"""Choix du seuil de décision pour la cible principale `abandon`, sur des probabilités.

Le modèle rend une **probabilité** ; décider « à risque / pas à risque » exige un seuil, qui
est une couche **externe** au modèle (D15). Faute d'un coût métier chiffré (l'énoncé ne le
fournit pas), le seuil ne se calcule pas : il se **déclare**, via une politique lisible - un
plancher de rappel, ou une capacité d'accompagnement. Le module fournit la table qui donne à
voir l'arbitrage, et la fonction qui applique une politique ; **le choix de la politique se
défend au notebook** (§9.3).

Toutes les mesures sont calculées sur des probabilités *out-of-fold* (train), jamais sur le
test - scellé jusqu'à §12.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve


def threshold_table(y, proba, *, thresholds: np.ndarray | None = None) -> pd.DataFrame:
    """Pour une grille de seuils, le volume d'alertes et l'arbitrage rappel / précision.

    Chaque ligne dit, pour un seuil : combien d'étudiants seraient signalés (`n_alertes`,
    la charge d'accompagnement, vrais et faux positifs confondus) et quelle part de la
    promotion cela représente (`pct_promo`) ; le rappel, la précision et leur synthèse `f2`
    (F-mesure pondérant le rappel 2× la précision, car rater un décrocheur - `n_FN` - coûte
    plus qu'une alerte à tort, D03) ; enfin `tp`, les décrocheurs effectivement signalés.
    Indexée par le seuil.
    """
    if thresholds is None:
        thresholds = np.round(np.arange(0.05, 0.96, 0.05), 2)
    y = np.asarray(y)
    proba = np.asarray(proba)
    n = len(y)
    positifs = int(y.sum())
    lignes = []
    for t in thresholds:
        signale = proba >= t
        tp = int(np.sum(signale & (y == 1)))
        fn = int(np.sum(~signale & (y == 1)))
        n_alertes = int(signale.sum())
        rappel = tp / positifs if positifs else 0.0
        precision = tp / n_alertes if n_alertes else 0.0
        # F2 : F-mesure avec beta=2, qui pondère le rappel 4× (beta²) plus que la précision.
        denom = 4 * precision + rappel
        f2 = 5 * precision * rappel / denom if denom else 0.0
        lignes.append(
            {
                "seuil": float(t),
                "rappel": rappel,
                "precision": precision,
                "f2": f2,
                "n_alertes": n_alertes,
                "tp": tp,
                "n_FN": fn,
                "pct_promo": n_alertes / n,
            }
        )
    return pd.DataFrame(lignes).set_index("seuil")


def pick_threshold(
    y,
    proba,
    *,
    recall_target: float | None = None,
    capacity_n: int | None = None,
    capacity_pct: float | None = None,
) -> float:
    """Applique **une** politique de seuil et renvoie le seuil correspondant.

    - `recall_target` - le plus haut seuil garantissant un rappel ≥ cible (attraper au moins
      cette part des décrocheurs) ; à défaut d'atteindre la cible, le seuil le plus bas ;
    - `capacity_n` - le seuil qui signale exactement les `n` étudiants les plus à risque ;
    - `capacity_pct` - idem, `n` déduit d'une part de la promotion.

    Exactement un critère doit être fourni.
    """
    fournis = [c is not None for c in (recall_target, capacity_n, capacity_pct)]
    if sum(fournis) != 1:
        raise ValueError(
            "Fournir exactement un critère : recall_target, capacity_n ou capacity_pct."
        )

    proba = np.asarray(proba)
    if recall_target is not None:
        # precision_recall_curve renvoie rappel décroissant quand le seuil croît ; on prend
        # le plus haut seuil dont le rappel tient encore la cible (le plus précis possible).
        _, rappel, seuils = precision_recall_curve(np.asarray(y), proba)
        eligibles = rappel[:-1] >= recall_target
        return float(seuils[eligibles].max()) if eligibles.any() else float(seuils.min())

    n = capacity_n if capacity_n is not None else round(capacity_pct * len(proba))
    n = max(1, min(n, len(proba)))
    # Le n-ième score le plus élevé : seuil qui laisse passer exactement n alertes (ex æquo près).
    return float(np.sort(proba)[::-1][n - 1])
