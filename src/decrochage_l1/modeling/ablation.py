"""Ablation — le coût du retrait d'un bloc de features, pour la minimisation (§8.6/§8.10, C4).

On minimise **par principe** (art. 5.1.c) : leurres, proxies et redondances sont retirés
par défaut. L'ablation ne sert pas à *inclure* une variable pour sa performance - elle
**quantifie le coût du retrait** d'un bloc, complet vs complet-sans-bloc, en prédictions
out-of-fold. Le verdict (conserver ou retirer) se lit au notebook : on ne conserve qu'en
cas de chute matérielle.

Deux entrées jumelles : `ablate` pour la classification (ROC-AUC, PR-AUC, indépendantes du
seuil), `ablate_regression` pour la régression (MAE, RMSE, R²). Toutes deux partagent les
mêmes scénarios : complet, complet-sans-chaque-bloc, et minimisé (tous les blocs retirés).
"""

from collections.abc import Callable

import pandas as pd

from decrochage_l1.modeling.evaluation import (
    classification_metrics,
    oof_pred,
    oof_proba,
    regression_metrics,
)


def _scenarios(all_features: list[str], blocks: dict[str, list[str]]) -> dict[str, list[str]]:
    """Nom de scénario → colonnes **conservées** : complet, sans chaque bloc, minimisé."""
    kept = {"complet": list(all_features)}
    for name, cols in blocks.items():
        kept[f"sans {name}"] = [c for c in all_features if c not in cols]
    union = {c for cols in blocks.values() for c in cols}
    kept["minimisé"] = [c for c in all_features if c not in union]
    return kept


def ablate(
    build_pipeline, X: pd.DataFrame, y: pd.Series, blocks: dict[str, list[str]], cv
) -> pd.DataFrame:
    """Coût du retrait de chaque bloc pour une **classification** (ROC-AUC, PR-AUC).

    `build_pipeline(features)` reçoit la liste des colonnes à garder et rend le `Pipeline`
    de la famille retenue, préprocesseur restreint à ces colonnes. Le tableau rendu porte,
    par scénario, les métriques OOF et leur écart au complet (`d_roc_auc`, `d_pr_auc`) - un
    écart négatif est le coût du retrait.
    """
    rows = []
    for name, kept in _scenarios(list(X.columns), blocks).items():
        proba = oof_proba(build_pipeline(kept), X[kept], y, cv)
        rows.append({"scenario": name, "n_features": len(kept), **classification_metrics(y, proba)})

    table = pd.DataFrame(rows).set_index("scenario")
    reference = table.loc["complet"]
    table["d_roc_auc"] = table["roc_auc"] - reference["roc_auc"]
    table["d_pr_auc"] = table["pr_auc"] - reference["pr_auc"]
    return table


def ablate_regression(
    build_pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    blocks: dict[str, list[str]],
    cv,
    *,
    postprocess: Callable | None = None,
) -> pd.DataFrame:
    """Coût du retrait de chaque bloc pour une **régression** (MAE, RMSE, R²).

    Jumelle de `ablate`. `postprocess` s'applique aux prédictions avant le calcul des
    métriques - p. ex. borner une note à [0, 20]. Un écart de MAE/RMSE positif (ou de R²
    négatif) est le coût du retrait.
    """
    postprocess = postprocess or (lambda pred: pred)
    rows = []
    for name, kept in _scenarios(list(X.columns), blocks).items():
        pred = postprocess(oof_pred(build_pipeline(kept), X[kept], y, cv))
        rows.append({"scenario": name, "n_features": len(kept), **regression_metrics(y, pred)})

    table = pd.DataFrame(rows).set_index("scenario")
    reference = table.loc["complet"]
    for metric in ("mae", "rmse", "r2"):
        table[f"d_{metric}"] = table[metric] - reference[metric]
    return table
