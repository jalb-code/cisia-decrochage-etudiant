"""Mesure de la dérive des entrées, **par campagne** — PSI et Kolmogorov-Smirnov.

Le régime réel du cas d'usage est d'environ deux extractions par an : la dérive se
mesure donc sur le **lot qu'on vient de scorer**, comparé à une distribution de
référence figée à l'entraînement, et non par un relevé continu qui donnerait l'illusion
d'une surveillance temps réel. C'est une propriété de la campagne, pas une ressource.

La décision se prend sur l'**amplitude** (PSI), pas sur la significativité : deux
échantillons d'une même population, aux effectifs d'une campagne, suffisent à produire un
écart statistiquement significatif. Le test de Kolmogorov-Smirnov ne sert donc **qu'en
garde négatif** — dire « PSI modéré mais effectif faible, on attend la campagne suivante ».

Aucune valeur de politique ici : seuils de surveillance/alerte et effectif minimal sont
**déclarés au notebook** (défaut sérialisé dans la fiche, surchargeable en exploitation) et
**passés en paramètre**. Le module porte la mesure, pas le seuil.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

# Verdicts, ordonnés du plus au moins grave — l'ordre sert le tri d'affichage.
STABLE = "stable"
A_SURVEILLER = "à surveiller"
ALERTE = "alerte"


@dataclass(frozen=True)
class VariableDrift:
    """Dérive mesurée pour une variable, entre référence et campagne courante."""

    variable: str
    psi: float
    ks_statistic: float
    ks_pvalue: float
    shift_std: (
        float | None
    )  # déplacement de moyenne en écarts-types de la référence (numérique seul)
    verdict: str


@dataclass(frozen=True)
class CampaignDrift:
    """Bilan de dérive d'une campagne — mesurable ou non, et le détail par variable."""

    mesurable: bool
    motif: str | None
    variables: tuple[VariableDrift, ...]
    psi_max: float
    verdict: str


def _psi_from_proportions(expected: np.ndarray, actual: np.ndarray, *, epsilon: float) -> float:
    """Indice de stabilité à partir de deux vecteurs de proportions alignés.

    `epsilon` remplace une proportion nulle pour éviter division et logarithme de zéro :
    une classe vide d'un côté rendrait l'indice infini sans lui.
    """
    exp = np.where(expected == 0, epsilon, expected)
    act = np.where(actual == 0, epsilon, actual)
    return float(np.sum((act - exp) * np.log(act / exp)))


def population_stability_index(
    expected: Sequence[float], actual: Sequence[float], *, bins: int = 10, epsilon: float = 1e-6
) -> float:
    """PSI d'une variable **numérique** : bornes de bacs prises sur les quantiles de la référence.

    Les bacs sont taillés sur la **référence** (et non sur le lot courant), pour que la
    dérive se lise comme un déplacement de la campagne *par rapport à* ce qui était attendu.
    Les bords extrêmes sont ouverts (±∞) : une valeur courante hors de l'étendue de
    référence tombe dans le premier ou le dernier bac au lieu d'être perdue.
    """
    expected_arr = pd.Series(expected, dtype="float64").dropna().to_numpy()
    actual_arr = pd.Series(actual, dtype="float64").dropna().to_numpy()
    if expected_arr.size == 0 or actual_arr.size == 0:
        return float("nan")

    quantiles = np.linspace(0, 1, bins + 1)
    edges = np.unique(np.quantile(expected_arr, quantiles))
    if edges.size < 2:  # référence constante : aucun bac exploitable
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf

    exp_counts = np.histogram(expected_arr, bins=edges)[0]
    act_counts = np.histogram(actual_arr, bins=edges)[0]
    exp_prop = exp_counts / exp_counts.sum()
    act_prop = act_counts / act_counts.sum()
    return _psi_from_proportions(exp_prop, act_prop, epsilon=epsilon)


def population_stability_index_categorical(
    expected: Sequence, actual: Sequence, *, epsilon: float = 1e-6
) -> float:
    """PSI d'une variable **catégorielle** : proportions comparées modalité à modalité.

    L'union des modalités des deux échantillons fixe l'axe : une modalité apparue dans la
    campagne mais absente de la référence est comptée, et pèse via `epsilon`.
    """
    exp_series = pd.Series(expected).dropna()
    act_series = pd.Series(actual).dropna()
    if exp_series.empty or act_series.empty:
        return float("nan")

    categories = sorted(set(exp_series.unique()) | set(act_series.unique()), key=str)
    exp_prop = (
        exp_series.value_counts().reindex(categories, fill_value=0) / len(exp_series)
    ).to_numpy()
    act_prop = (
        act_series.value_counts().reindex(categories, fill_value=0) / len(act_series)
    ).to_numpy()
    return _psi_from_proportions(exp_prop, act_prop, epsilon=epsilon)


def _verdict(psi: float, *, seuil_surveillance: float, seuil_alerte: float) -> str:
    """Range un PSI dans l'un des trois verdicts, selon les seuils passés."""
    if np.isnan(psi):
        return STABLE
    if psi >= seuil_alerte:
        return ALERTE
    if psi >= seuil_surveillance:
        return A_SURVEILLER
    return STABLE


def _shift_std(expected: np.ndarray, actual: np.ndarray) -> float | None:
    """Déplacement de moyenne exprimé en écarts-types de la référence, ou None si σ nul."""
    std = expected.std()
    if std == 0 or np.isnan(std):
        return None
    return float((actual.mean() - expected.mean()) / std)


def assess(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    numeric: Sequence[str] = (),
    categorical: Sequence[str] = (),
    seuil_surveillance: float,
    seuil_alerte: float,
    effectif_min: int,
    bins: int = 10,
) -> CampaignDrift:
    """Bilan de dérive d'une campagne, variable par variable, sous une taille minimale.

    Sous `effectif_min`, la campagne est déclarée **non mesurable** avec son motif plutôt
    que de publier un indice sur trop peu de dossiers : refuser de scorer serait punir la
    campagne pour un défaut d'outillage — la prédiction, elle, reste servie par ailleurs.

    Chaque variable reçoit son PSI (numérique par bacs, catégoriel par proportions), son
    test KS et — pour le numérique — son déplacement en écarts-types. Le verdict global est
    celui de la variable la plus dérivée.
    """
    n = len(current)
    if n < effectif_min:
        motif = f"campagne de {n} dossiers : dérive non mesurable sous {effectif_min}"
        return CampaignDrift(
            mesurable=False, motif=motif, variables=(), psi_max=float("nan"), verdict=STABLE
        )

    results: list[VariableDrift] = []
    for column in numeric:
        exp = pd.Series(reference[column], dtype="float64").dropna().to_numpy()
        act = pd.Series(current[column], dtype="float64").dropna().to_numpy()
        psi = population_stability_index(exp, act, bins=bins)
        ks = ks_2samp(exp, act) if exp.size and act.size else None
        results.append(
            VariableDrift(
                variable=column,
                psi=psi,
                ks_statistic=float(ks.statistic) if ks else float("nan"),
                ks_pvalue=float(ks.pvalue) if ks else float("nan"),
                shift_std=_shift_std(exp, act) if exp.size and act.size else None,
                verdict=_verdict(
                    psi, seuil_surveillance=seuil_surveillance, seuil_alerte=seuil_alerte
                ),
            )
        )
    for column in categorical:
        psi = population_stability_index_categorical(reference[column], current[column])
        results.append(
            VariableDrift(
                variable=column,
                psi=psi,
                ks_statistic=float("nan"),
                ks_pvalue=float("nan"),
                shift_std=None,
                verdict=_verdict(
                    psi, seuil_surveillance=seuil_surveillance, seuil_alerte=seuil_alerte
                ),
            )
        )

    # Tri par PSI décroissant : la variable la plus dérivée en tête, la lecture suit l'action.
    results.sort(key=lambda v: float("-inf") if np.isnan(v.psi) else v.psi, reverse=True)
    psi_values = [v.psi for v in results if not np.isnan(v.psi)]
    psi_max = max(psi_values) if psi_values else float("nan")
    verdict = _verdict(psi_max, seuil_surveillance=seuil_surveillance, seuil_alerte=seuil_alerte)
    return CampaignDrift(
        mesurable=True, motif=None, variables=tuple(results), psi_max=psi_max, verdict=verdict
    )
