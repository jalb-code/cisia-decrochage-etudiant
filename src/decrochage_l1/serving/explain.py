"""Explicabilité par contributions **analytiques** d'un modèle linéaire (log-cote additive).

Le classifieur retenu (§8) est une régression logistique : la log-cote d'un dossier est
*exactement* `intercept + Σ coef_j · z_j` sur les features préprocessées `z`. Les
contributions sont donc **additives et signées** — une longueur de barre a un sens exact,
ce qui légitime un visuel en barres divergentes (protège / aggrave). Aucune approximation,
donc **aucun SHAP** : la bibliothèque est écartée de l'image d'inférence (éco-conception),
et n'intervient qu'au notebook (§12) pour la confirmation globale.

L'agrégation par thème suppose la **liste complète** des contributions : un modèle linéaire
étant additif, la contribution d'un thème est la somme exacte de ses variables — agréger un
sous-ensemble donnerait un thème faussement neutre. Les thèmes sont **passés en paramètre**
(déclarés au notebook, sérialisés dans la fiche), jamais codés ici.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# Thème d'accueil des variables sans thème déclaré : rend l'agrégation exhaustive plutôt
# que de perdre silencieusement une contribution (ce qui fausserait le total d'un thème).
UNGROUPED = "autres"


@dataclass(frozen=True)
class Contributions:
    """Décomposition additive d'une prédiction linéaire, en log-cote et en probabilité."""

    base_logit: float  # l'ordonnée à l'origine : la log-cote « de départ »
    by_variable: dict[str, float]  # contribution nette de chaque variable source
    by_theme: dict[str, float]  # contributions regroupées par thème (somme exacte)
    total_logit: float  # base + Σ contributions == log-cote du modèle
    probability: float  # σ(total_logit) == proba prédite de la classe positive


def _find_onehot(transformer) -> OneHotEncoder | None:
    """Repère un `OneHotEncoder` dans un transformateur, seul ou au bout d'un `Pipeline`."""
    if isinstance(transformer, OneHotEncoder):
        return transformer
    if isinstance(transformer, Pipeline):
        for _, step in transformer.steps:
            if isinstance(step, OneHotEncoder):
                return step
    return None


def _column_transformer(estimator) -> ColumnTransformer:
    """Extrait le `ColumnTransformer` d'un pipeline (ou le renvoie s'il en est déjà un).

    On le cherche parmi les étapes, la dernière transformation apprise du pipeline étant
    ici le préprocesseur : c'est elle qui fixe l'ordre des colonnes de sortie, donc
    l'alignement avec `coef_`.
    """
    if isinstance(estimator, ColumnTransformer):
        return estimator
    if isinstance(estimator, Pipeline):
        for _, step in reversed(estimator.steps):
            if isinstance(step, ColumnTransformer):
                return step
    raise ValueError("aucun ColumnTransformer trouvé dans le pipeline.")


def source_columns(column_transformer: ColumnTransformer) -> list[str]:
    """Aligne chaque colonne de sortie du préprocesseur sur sa **variable source**.

    Le `ColumnTransformer` concatène ses blocs dans l'ordre de déclaration : numérique et
    ordinal sortent une colonne par variable (1:1), le one-hot en sort autant que la
    variable a de modalités. On reconstitue donc l'origine bloc par bloc, en dépliant le
    one-hot par ses `categories_`. Le résultat est aligné, position à position, sur
    `model.coef_` — ce qui permet de replier les contributions vers les variables métier.
    """
    sources: list[str] = []
    for name, transformer, columns in column_transformer.transformers_:
        if transformer in ("drop", None):
            continue
        if name == "remainder":
            if transformer == "passthrough":
                sources.extend(list(columns))
            continue
        onehot = _find_onehot(transformer)
        if onehot is not None:
            for column, categories in zip(columns, onehot.categories_, strict=True):
                sources.extend([column] * len(categories))
        else:
            sources.extend(list(columns))
    return sources


def _sigmoid(x: float) -> float:
    """Fonction logistique, stable pour de grandes valeurs positives comme négatives."""
    return float(1.0 / (1.0 + np.exp(-x)))


def _single_row_frame(row: Mapping | pd.Series | pd.DataFrame) -> pd.DataFrame:
    """Ramène un dossier — dict, Series ou DataFrame d'une ligne — à un DataFrame d'une ligne."""
    if isinstance(row, pd.DataFrame):
        return row
    if isinstance(row, pd.Series):
        return row.to_frame().T
    return pd.DataFrame([dict(row)])


def contributions(
    pipeline: Pipeline,
    row: Mapping | pd.Series | pd.DataFrame,
    *,
    themes: Mapping[str, str] | None = None,
) -> Contributions:
    """Décompose la prédiction d'un dossier en contributions par variable, puis par thème.

    `pipeline` est un `Pipeline([préprocesseur…, modèle linéaire])` déjà `fit` : le dernier
    maillon porte `coef_`/`intercept_`, les précédents transforment. La log-cote totale
    reconstituée égale, à la précision numérique, `decision_function(row)` du pipeline —
    c'est la garantie que la décomposition est exacte et non une approximation.

    `themes` associe une variable source à son thème ; toute variable non déclarée tombe
    dans `UNGROUPED`, pour que la somme des thèmes égale la somme des variables.
    """
    frame = _single_row_frame(row)
    if len(frame) != 1:
        raise ValueError("contributions() attend un dossier unique (une ligne).")

    model = pipeline[-1]
    transformed = np.asarray(pipeline[:-1].transform(frame), dtype="float64")[0]

    coef = np.asarray(model.coef_, dtype="float64").ravel()
    intercept = float(np.asarray(model.intercept_, dtype="float64").ravel()[0])
    if coef.shape[0] != transformed.shape[0]:
        raise ValueError("coefficients et sortie du préprocesseur de tailles différentes.")

    per_output = coef * transformed
    sources = source_columns(_column_transformer(pipeline))
    if len(sources) != per_output.shape[0]:
        raise ValueError("cartographie des colonnes source incohérente avec les coefficients.")

    by_variable: dict[str, float] = {}
    for source, value in zip(sources, per_output, strict=True):
        by_variable[source] = by_variable.get(source, 0.0) + float(value)

    by_theme: dict[str, float] = {}
    for variable, value in by_variable.items():
        theme = themes.get(variable, UNGROUPED) if themes else UNGROUPED
        by_theme[theme] = by_theme.get(theme, 0.0) + value

    total_logit = intercept + float(per_output.sum())
    return Contributions(
        base_logit=intercept,
        by_variable=by_variable,
        by_theme=by_theme,
        total_logit=total_logit,
        probability=_sigmoid(total_logit),
    )
