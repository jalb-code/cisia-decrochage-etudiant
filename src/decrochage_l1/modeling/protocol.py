"""Protocole d'évaluation — le split scellé et la validation croisée (C5).

Deux gestes, et rien d'autre : **partitionner** le jeu en train / test (le test scellé
jusqu'à la mesure finale, §12), et **fabriquer** l'objet de validation croisée qui
rejouera l'entraînement sur le seul train. Le module ne décide ni la cible, ni la
taille du test, ni la graine : ce sont des paramètres, défendus au notebook.

La stratification préserve le taux de la classe positive - un test qui ne refléterait
pas le déséquilibre fausserait toute mesure de rang (ROC-AUC, PR-AUC). Pour une cible
**continue** (régression), la stratification n'a pas de sens : `make_cv(stratified=False)`
rend un `KFold` simple.
"""

import pandas as pd
from sklearn.model_selection import KFold, StratifiedKFold, train_test_split


def make_split(
    df: pd.DataFrame, target: str, *, test_size: float = 0.2, seed: int = 0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Partitionne `df` en (train, test) **stratifiés** sur `target`, test scellé.

    Toutes les colonnes sont conservées de part et d'autre - y compris les variables
    protégées hors modèle, dont l'audit d'équité (§12) a besoin sur le test. La
    séparation X / y se fait ensuite, au notebook, en retirant cibles et hors-modèle.
    """
    train_df, test_df = train_test_split(
        df, test_size=test_size, random_state=seed, stratify=df[target]
    )
    return train_df.reset_index(drop=True), test_df.reset_index(drop=True)


def make_cv(*, n_splits: int = 5, seed: int = 0, stratified: bool = True):
    """Rend l'objet de validation croisée - `StratifiedKFold` par défaut, `KFold` sinon.

    `shuffle=True` car les lignes n'ont aucun ordre temporel exploitable ; la graine
    fixe le mélange, pour que deux exécutions donnent les mêmes plis (reproductibilité).
    """
    if stratified:
        return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return KFold(n_splits=n_splits, shuffle=True, random_state=seed)
