"""Mesures — métriques, prédictions out-of-fold, courbes de diagnostic (C4).

Toutes les mesures de comparaison passent par des prédictions **out-of-fold** : chaque
ligne est prédite par un modèle qui ne l'a pas vue à l'entraînement. C'est une estimation
honnête de la généralisation, sans jamais toucher au test scellé.

Le module calcule et trace ; il ne décide d'aucun seuil - les métriques retenues sont
**indépendantes du seuil** (rang et calibration), le point de fonctionnement se choisit
en §9. Le module ne connaît pas non plus le sens métier des chiffres : il les rend, le
notebook les lit.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_curve,
    r2_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import cross_val_predict, cross_val_score


def oof_proba(pipeline, X: pd.DataFrame, y: pd.Series, cv) -> np.ndarray:
    """Probabilité de la classe positive, out-of-fold, pour chaque ligne."""
    return cross_val_predict(pipeline, X, y, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]


def classification_metrics(y: pd.Series, proba: np.ndarray) -> dict[str, float]:
    """Trois mesures indépendantes du seuil : rang global, rang sur la minorité, calibration.

    - `roc_auc` - rang, adaptée au déséquilibre modéré, indépendante du seuil (D03) ;
    - `pr_auc`  - précision-rappel, centrée sur la classe positive minoritaire ;
    - `brier`   - erreur quadratique de la probabilité, plus bas = mieux calibré.
    """
    return {
        "roc_auc": roc_auc_score(y, proba),
        "pr_auc": average_precision_score(y, proba),
        "brier": brier_score_loss(y, proba),
    }


def cv_scores(
    pipeline, X: pd.DataFrame, y: pd.Series, cv, *, scoring: str = "roc_auc"
) -> np.ndarray:
    """Score du critère `scoring` **pli par pli** - pour lire la dispersion, pas que la moyenne.

    Un écart de moyenne entre deux familles n'a de sens qu'au regard de l'écart-type
    inter-plis : s'il ne le dépasse pas, le classement n'est pas discriminant.
    """
    return cross_val_score(pipeline, X, y, cv=cv, scoring=scoring, n_jobs=-1)


def train_vs_oof(pipeline, X: pd.DataFrame, y: pd.Series, cv) -> dict[str, float]:
    """Diagnostic de sur-ajustement : ROC-AUC en resubstitution vs out-of-fold.

    Un écart large (train ≫ oof) signale que le modèle mémorise plus qu'il ne généralise.
    """
    fitted = clone(pipeline).fit(X, y)
    train_proba = fitted.predict_proba(X)[:, 1]
    oof = oof_proba(clone(pipeline), X, y, cv)
    return {
        "train_roc_auc": roc_auc_score(y, train_proba),
        "oof_roc_auc": roc_auc_score(y, oof),
    }


def oof_pred(regressor, X: pd.DataFrame, y: pd.Series, cv) -> np.ndarray:
    """Prédiction continue out-of-fold, pour la cible secondaire `moyenne_finale`."""
    return cross_val_predict(regressor, X, y, cv=cv, n_jobs=-1)


def plot_regression_fit(y: pd.Series, pred: np.ndarray, ax: plt.Axes | None = None) -> plt.Axes:
    """Nuage note réelle vs note prédite ; la diagonale marque la prédiction parfaite."""
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(y, pred, s=8, alpha=0.3)
    bornes = [min(np.min(y), np.min(pred)), max(np.max(y), np.max(pred))]
    ax.plot(bornes, bornes, "--", color="grey", linewidth=1)
    ax.set(
        xlabel="Note finale réelle (/20)",
        ylabel="Note prédite (/20)",
        title="Note réelle vs prédite (OOF)",
    )
    return ax


def regression_metrics(y: pd.Series, pred: np.ndarray) -> dict[str, float]:
    """Erreur de régression en points/20 (MAE, RMSE) et part de variance expliquée (R²)."""
    return {
        "mae": mean_absolute_error(y, pred),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "r2": r2_score(y, pred),
    }


def plot_roc(y: pd.Series, probas: dict[str, np.ndarray], ax: plt.Axes | None = None) -> plt.Axes:
    """Courbes ROC superposées, une par famille, l'AUC portée dans la légende."""
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    for name, proba in probas.items():
        fpr, tpr, _ = roc_curve(y, proba)
        ax.plot(fpr, tpr, label=f"{name} · AUC {roc_auc_score(y, proba):.3f}")
    ax.plot([0, 1], [0, 1], "--", color="grey", linewidth=1)  # le hasard
    ax.set(
        xlabel="Taux de faux positifs",
        ylabel="Taux de vrais positifs",
        title="Courbes ROC (OOF)",
    )
    ax.legend(loc="lower right")
    return ax


def plot_pr(y: pd.Series, probas: dict[str, np.ndarray], ax: plt.Axes | None = None) -> plt.Axes:
    """Courbes précision-rappel superposées ; la ligne de base = la prévalence."""
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    for name, proba in probas.items():
        precision, recall, _ = precision_recall_curve(y, proba)
        ax.plot(recall, precision, label=f"{name} · PR-AUC {average_precision_score(y, proba):.3f}")
    ax.axhline(float(np.mean(y)), linestyle="--", color="grey", linewidth=1)  # prévalence
    ax.set(xlabel="Rappel", ylabel="Précision", title="Courbes précision-rappel (OOF)")
    ax.legend(loc="upper right")
    return ax


def plot_score_distribution(
    y: pd.Series, proba: np.ndarray, *, bins: int = 30, ax: plt.Axes | None = None
) -> plt.Axes:
    """Histogrammes des probabilités prédites, séparés par classe réelle.

    Rend visible la **séparation** : si le modèle sépare bien, les décrocheurs se massent
    vers les probabilités hautes, le reste vers les basses.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 4))
    y = np.asarray(y)
    ax.hist(proba[y == 0], bins=bins, alpha=0.6, label="reste (0)")
    ax.hist(proba[y == 1], bins=bins, alpha=0.6, label="abandon (1)")
    ax.set(
        xlabel="Probabilité d'abandon prédite",
        ylabel="Nombre d'étudiants",
        title="Répartition des probabilités par classe réelle",
    )
    ax.legend()
    return ax


def plot_ablation_cost(
    table: pd.DataFrame,
    *,
    cols: tuple[str, str] = ("d_roc_auc", "d_pr_auc"),
    labels: tuple[str, str] = ("Δ ROC-AUC", "Δ PR-AUC"),
    xlabel: str = "Écart au jeu complet (négatif = coût du retrait)",
    ax: plt.Axes | None = None,
) -> plt.Axes:
    """Coût du retrait de chaque bloc - barres des deux écarts `cols` (0 = jeu complet).

    Défauts pour la classification (Δ ROC-AUC, Δ PR-AUC) ; pour la régression, passer
    `cols=("d_mae", "d_rmse")` et l'`xlabel` adapté (un écart positif y est le coût).
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 4))
    scenarios = [s for s in table.index if s != "complet"]
    positions = np.arange(len(scenarios))
    ax.barh(positions - 0.2, table.loc[scenarios, cols[0]], height=0.4, label=labels[0])
    ax.barh(positions + 0.2, table.loc[scenarios, cols[1]], height=0.4, label=labels[1])
    ax.axvline(0, color="grey", linewidth=1)
    ax.set_yticks(positions, scenarios)
    ax.set(xlabel=xlabel, title="Coût de la minimisation")
    ax.legend()
    return ax


def plot_calibration(
    y: pd.Series, probas: dict[str, np.ndarray], *, n_bins: int = 10, ax: plt.Axes | None = None
) -> plt.Axes:
    """Diagrammes de fiabilité : probabilité prédite vs fréquence observée, par famille."""
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    for name, proba in probas.items():
        frac_pos, mean_pred = calibration_curve(y, proba, n_bins=n_bins, strategy="quantile")
        ax.plot(mean_pred, frac_pos, marker="o", markersize=4, label=name)
    ax.plot([0, 1], [0, 1], "--", color="grey", linewidth=1)  # calibration parfaite
    ax.set(
        xlabel="Probabilité prédite",
        ylabel="Fréquence observée",
        title="Courbes de calibration (OOF)",
    )
    ax.legend(loc="upper left")
    return ax


def plot_confusion(
    y: pd.Series,
    proba: np.ndarray,
    threshold: float,
    *,
    ax: plt.Axes | None = None,
    title: str | None = None,
) -> plt.Axes:
    """Matrice de confusion pour un seuil donné, appliqué aux probabilités fournies.

    L'étudiant est signalé quand sa probabilité atteint `threshold`. Chaque case porte son
    **type** (`TN` / `FP` / `FN` / `TP`) et son décompte ; les axes portent la classe réelle
    (lignes) et prédite (colonnes). Le *sens métier* des cases (FN = décrocheur manqué…) et la
    nature des probabilités (out-of-fold, test scellé) se disent au notebook.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(3.6, 3.2))
    pred = (np.asarray(proba) >= threshold).astype(int)
    # matrice[i, j] : i = classe réelle, j = classe prédite (labels 0 = reste, 1 = abandon).
    matrice = confusion_matrix(np.asarray(y), pred, labels=[0, 1])
    types = np.array([["TN", "FP"], ["FN", "TP"]])  # sens de chaque case, aligné sur matrice
    ax.imshow(matrice, cmap="Blues")
    seuil_texte = matrice.max() / 2  # texte blanc sur case foncée, noir sur case claire
    for i in range(2):
        for j in range(2):
            couleur = "white" if matrice[i, j] > seuil_texte else "black"
            ax.text(
                j,
                i,
                f"{types[i, j]}\n{matrice[i, j]:d}",
                ha="center",
                va="center",
                color=couleur,
                fontweight="bold",
            )
    ax.set(
        xticks=[0, 1],
        yticks=[0, 1],
        xticklabels=["reste", "abandon"],
        yticklabels=["reste", "abandon"],
        xlabel="Prédiction",
        ylabel="Réel",
        title=title or f"Seuil {threshold:.2f}",
    )
    ax.grid(False)  # sinon la grille du style traverse les cases (ticks au centre des cellules)
    return ax
