"""Préprocesseur appris — imputation, encodage, scaling, dans le `Pipeline` (C4).

Ce que ce module fabrique est un `ColumnTransformer` : il **apprend** ses paramètres
(médiane, moyenne/écart-type) sur les données qu'on lui donne. Placé dans un `Pipeline`,
il est donc `fit` **à l'intérieur** de chaque pli de validation croisée, jamais figé sur
le train entier avant elle - c'est la garantie anti-fuite.

Le module ne décide **rien** : ni quelles colonnes sont numériques, ordinales ou
nominales, ni le vocabulaire des modalités. Le typage (un jugement : traiter les échelles
de Likert en numérique, exclure les protégées) vient du notebook ; l'inventaire des
modalités (un fait mesuré à l'EDA) vient de `preparation` - déclaré, jamais déduit du
train, pour qu'une modalité rare absente d'un pli ne fasse pas disparaître sa colonne.

Traitement par type :

- **numérique** - imputation médiane (robuste à l'asymétrie, l'absence n'y vaut pas 0),
  puis scaling **si demandé** (famille linéaire seule) ;
- **ordinal** - encodage selon l'ordre déclaré, puis imputation médiane (une modalité
  hors-ordre casserait l'échelle), puis scaling si demandé ;
- **nominal** - une modalité d'absence explicite si besoin, puis one-hot avec le
  vocabulaire déclaré et `handle_unknown="ignore"` (une modalité inconnue → tout à zéro,
  jamais une erreur).
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

# Modalité d'absence de `etablissement_origine` : l'absence = non-fourni, à conserver
# comme une catégorie de plein droit (branche métier D09), pas à imputer par un mode.
MISSING_CATEGORY = "inconnu"


def to_numpy_dtypes(data: pd.DataFrame) -> pd.DataFrame:
    """Convertit les dtypes pandas **nullables** (Int64, string…) en dtypes **numpy**.

    Le gold en mémoire hérite de dtypes nullables de la conformation ; scikit-learn
    travaille en numpy et bute sur `pd.NA` (« boolean value of NA is ambiguous »). Cette
    conversion aligne l'entrée sur ce que produirait une relecture CSV : `pd.NA` devient
    `np.nan`, les entiers deviennent des flottants (un entier à trous n'a pas d'équivalent
    numpy sans `NaN`), les chaînes deviennent des `object`. Sans effet sur un jeu déjà numpy.
    """
    out = data.copy()
    for column in out.columns:
        dtype = out[column].dtype
        if not pd.api.types.is_extension_array_dtype(dtype):
            continue
        if pd.api.types.is_numeric_dtype(dtype):
            out[column] = out[column].astype("float64")
        else:  # chaîne / booléen nullable : object avec np.nan à la place de pd.NA
            out[column] = out[column].astype(object).where(out[column].notna(), np.nan)
    return out


def resolve_categories(
    declared: dict[str, tuple[str, ...]],
    data: pd.DataFrame,
    columns: list[str],
    *,
    extend: bool = True,
) -> tuple[list[list[str]], dict[str, list[str]]]:
    """Concilie l'inventaire **déclaré** et les modalités **présentes** dans le jeu.

    Pour chaque colonne, les modalités déclarées viennent d'abord - position stable, une
    modalité rare garde sa colonne même absente du train (garde-fou anti-disparition) -
    puis, si `extend`, toute modalité du jeu non déclarée est ajoutée à la suite. Les
    modalités inédites sont aussi renvoyées à part (`extras`) : un ré-entraînement les
    **signale à l'humain** plutôt que de les laisser passer en silence.

    `extend=True` pour le nominal (une modalité inédite mérite sa colonne) ; `extend=False`
    pour l'ordinal, où une modalité hors échelle n'a pas d'ordre défini - on la signale
    sans l'insérer, l'encodeur la traitera comme inconnue.
    """
    categories: list[list[str]] = []
    extras: dict[str, list[str]] = {}
    for column in columns:
        declared_col = list(declared[column])
        observed = sorted(v for v in data[column].dropna().unique() if v not in declared_col)
        categories.append(declared_col + observed if extend else declared_col)
        if observed:
            extras[column] = observed
    return categories, extras


def make_preprocessor(
    *,
    numeric: list[str],
    ordinal: list[str],
    onehot: list[str],
    ordinal_categories: list[list[str]],
    onehot_categories: list[list[str]],
    scale: bool,
) -> ColumnTransformer:
    """Assemble le `ColumnTransformer` par type de colonne, scaling optionnel.

    `ordinal_categories` et `onehot_categories` sont alignés, dans l'ordre, sur `ordinal`
    et `onehot` : à chaque colonne sa liste de modalités déclarée. `scale` n'a d'effet
    que sur les blocs numérique et ordinal, et ne sert qu'aux familles linéaires - les
    ensembles d'arbres y sont indifférents.
    """
    numeric_steps: list = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        numeric_steps.append(("scale", StandardScaler()))

    ordinal_steps: list = [
        (
            "encode",
            OrdinalEncoder(
                categories=ordinal_categories,
                handle_unknown="use_encoded_value",
                unknown_value=np.nan,
            ),
        ),
        ("impute", SimpleImputer(strategy="median")),
    ]
    if scale:
        ordinal_steps.append(("scale", StandardScaler()))

    onehot_pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="constant", fill_value=MISSING_CATEGORY)),
            (
                "encode",
                OneHotEncoder(
                    categories=onehot_categories,
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
            ),
        ]
    )

    return ColumnTransformer(
        [
            ("num", Pipeline(numeric_steps), numeric),
            ("ord", Pipeline(ordinal_steps), ordinal),
            ("cat", onehot_pipe, onehot),
        ],
        remainder="drop",
    )
