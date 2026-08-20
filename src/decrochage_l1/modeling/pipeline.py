"""Construction des deux pipelines retenus, à partir de la spec figée (§8-§9, industrialisé).

Ce module **ré-exprime** pour l'industrialisation ce que le notebook construit en §8-§9 : le
pipeline `abandon` (régression logistique, préprocesseur avec scaling) et le pipeline
`moyenne_finale` (gradient boosting, sans scaling). Il ne passe **pas** par `modeling.families`
- qui instancie les trois familles candidates et tire `xgboost` (groupe `analysis`, hors
runtime) : la CLI n'a besoin que des deux familles éprouvées, avec leurs hyperparamètres
**gelés dans la spec** (D44), jamais ré-optimisés ici. La légère duplication de `families` est
assumée (industrialiser transcrit le choix défendu au notebook, sans refactorer celui-ci).

Le préprocesseur reste `preprocessing.make_preprocessor` (partagé avec le notebook) et le
vocabulaire catégoriel `data.preparation` : une modalité déclarée garde sa colonne même
absente d'un jeu neuf.
"""

import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from decrochage_l1.data import preparation
from decrochage_l1.modeling import preprocessing
from decrochage_l1.modeling.spec import PipelineSpec


def build_preprocessor(
    spec: PipelineSpec, reference: pd.DataFrame, features: list[str], *, scale: bool
) -> object:
    """Assemble le préprocesseur restreint à `features`, comme `construire_preprocesseur` (§8).

    Les rôles viennent de la spec (déclarés, non déduits) ; les modalités, du vocabulaire
    déclaré dans `data.preparation`, étendu des modalités observées dans `reference` pour le
    nominal (une inédite garde sa colonne), figé pour l'ordinal (hors échelle = inconnue).
    """
    numeric, ordinal, nominal = spec.feature_roles(list(reference.columns))
    num = [c for c in numeric if c in features]
    ordc = [c for c in ordinal if c in features]
    nomc = [c for c in nominal if c in features]
    ordinal_categories, _ = preprocessing.resolve_categories(
        preparation.ORDINAL_MODALITIES, reference, ordc, extend=False
    )
    onehot_categories, _ = preprocessing.resolve_categories(
        preparation.NOMINAL_MODALITIES, reference, nomc, extend=True
    )
    return preprocessing.make_preprocessor(
        numeric=num,
        ordinal=ordc,
        onehot=nomc,
        ordinal_categories=ordinal_categories,
        onehot_categories=onehot_categories,
        scale=scale,
    )


def build_classifier(spec: PipelineSpec, reference: pd.DataFrame, features: list[str]) -> Pipeline:
    """Pipeline `abandon` : préprocesseur (avec scaling) + régression logistique (HP gelés)."""
    preproc = build_preprocessor(spec, reference, features, scale=True)
    # Seul `C` est passé : la pénalité retenue est L2, qui est le défaut de scikit-learn
    # (le passer explicitement déclenche une dépréciation) ; le « pourquoi » du C=0,1 vit au
    # journal §9 (D30), pas ici.
    model = LogisticRegression(
        C=spec.hyperparams_classifier["C"],
        max_iter=1000,
        random_state=spec.seed,
    )
    return Pipeline([("prep", preproc), ("model", model)])


def build_regressor(spec: PipelineSpec, reference: pd.DataFrame, features: list[str]) -> Pipeline:
    """Pipeline `moyenne_finale` : préprocesseur (sans scaling) + gradient boosting (défauts §8)."""
    preproc = build_preprocessor(spec, reference, features, scale=False)
    model = GradientBoostingRegressor(random_state=spec.seed)
    return Pipeline([("prep", preproc), ("model", model)])
