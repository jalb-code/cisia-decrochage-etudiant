"""Familles de modèles candidates — chacune préprocesseur + estimateur, en un `Pipeline`.

Le préprocesseur vit **dans** le pipeline : la validation croisée le ré-ajuste à chaque
pli, sans fuite. Deux préprocesseurs reçus - `preproc_linear` (avec scaling) pour la
famille linéaire, `preproc_tree` (sans scaling) pour les ensembles d'arbres, qui y sont
indifférents. Chaque pipeline en reçoit une **copie** (`clone`) : deux modèles ne doivent
jamais partager un même transformateur ajustable.

Le module ne choisit pas la famille - il les instancie toutes, à armes égales ; le choix
se décide au notebook (§8.5) sur les mesures. Aucun rééquilibrage de classes ici : la
pondération se décide en §9, mesurée contre un témoin non pondéré.
"""

from sklearn.base import clone
from sklearn.ensemble import (
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier


def build_classifiers(*, preproc_linear, preproc_tree, seed: int = 0) -> dict[str, Pipeline]:
    """Les trois familles de classification, chacune dans son `Pipeline` (préproc + modèle).

    Linéaire régularisée (LogReg, la référence interprétable), forêt aléatoire et gradient
    boosting (non linéaires, robustes à la colinéarité du bloc d'engagement) - comparer
    linéaire et arbres est l'enjeu posé à l'EDA (§6.6).
    """
    return {
        "logreg": Pipeline(
            [
                ("prep", clone(preproc_linear)),
                ("model", LogisticRegression(max_iter=1000, random_state=seed)),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("prep", clone(preproc_tree)),
                ("model", RandomForestClassifier(random_state=seed, n_jobs=-1)),
            ]
        ),
        "xgboost": Pipeline(
            [
                ("prep", clone(preproc_tree)),
                (
                    "model",
                    XGBClassifier(random_state=seed, eval_metric="logloss", tree_method="hist"),
                ),
            ]
        ),
    }


def build_regressors(*, preproc_linear, preproc_tree, seed: int = 0) -> dict[str, Pipeline]:
    """Les trois familles de régression pour la cible secondaire `moyenne_finale` (/20)."""
    return {
        # Ridge : solveur par défaut déterministe, pas de `random_state` (il serait inerte).
        "ridge": Pipeline([("prep", clone(preproc_linear)), ("model", Ridge())]),
        "random_forest": Pipeline(
            [
                ("prep", clone(preproc_tree)),
                ("model", RandomForestRegressor(random_state=seed, n_jobs=-1)),
            ]
        ),
        "gradient_boosting": Pipeline(
            [
                ("prep", clone(preproc_tree)),
                ("model", GradientBoostingRegressor(random_state=seed)),
            ]
        ),
    }
