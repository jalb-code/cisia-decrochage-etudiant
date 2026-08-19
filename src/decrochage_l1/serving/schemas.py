"""Schémas d'entrée et de sortie du service — enveloppes de requête et mise en forme JSON.

Le dossier n'est **pas** un modèle Pydantic à champs figés : ses colonnes, bornes et
modalités viennent de la fiche (runtime), pas d'une déclaration statique. Le contrat que
consomme le client est donc publié par `/v1/modele` (`fiche_to_dict`), d'où l'interface
génère son formulaire — plutôt que recopié dans un schéma qui mentirait au premier
changement. Ici : l'enveloppe des requêtes, et les fonctions qui rendent les objets du
service en dictionnaires JSON-sérialisables (NaN ramené à `null`).
"""

import math
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from decrochage_l1.serving.contract import ServiceContract
from decrochage_l1.serving.drift import CampaignDrift
from decrochage_l1.serving.explain import Contributions
from decrochage_l1.serving.scoring import DossierScore
from decrochage_l1.serving.validation import RowRejection

# Mention systématique en sortie : matérialise l'absence de décision automatisée (art. 22).
AVERTISSEMENT = (
    "Aide à la décision : l'équipe pédagogique conserve la décision d'accompagnement. "
    "Aucun étudiant n'est contacté automatiquement. Les facteurs présentés sont des "
    "corrélations, pas des causes."
)

LOT_MAX = 10_000  # plafond d'un lot : un refus explicite plutôt qu'un épuisement mémoire


class CampaignRequest(BaseModel):
    """Un lot de dossiers bruts. `list[dict]` **délibérément** : une ligne invalide ne doit
    pas faire échouer la requête entière — chaque ligne est validée séparément.
    """

    dossiers: list[dict[str, Any]] = Field(min_length=1, max_length=LOT_MAX)


def _clean(value: Any) -> Any:
    """Ramène un flottant `NaN` à `null` : le JSON ne représente pas NaN."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def contributions_to_dict(contributions: Contributions, *, top: int | None = None) -> dict:
    """Contributions triées par amplitude ; `top` limite aux plus fortes (vue campagne)."""
    by_variable = sorted(contributions.by_variable.items(), key=lambda kv: abs(kv[1]), reverse=True)
    if top is not None:
        by_variable = by_variable[:top]
    by_theme = sorted(contributions.by_theme.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return {
        "base_logit": contributions.base_logit,
        "total_logit": contributions.total_logit,
        "probability": contributions.probability,
        "by_variable": [{"variable": k, "contribution": v} for k, v in by_variable],
        "by_theme": [{"theme": k, "contribution": v} for k, v in by_theme],
    }


def score_to_dict(score: DossierScore, *, top: int | None = None) -> dict:
    """Résultat d'un dossier en JSON ; `top` tronque aux contributions les plus fortes."""
    return {
        "reference": score.reference,
        "probability": score.probability,
        "moyenne_finale": score.moyenne_finale,
        "signaled": score.signaled,
        "contributions": contributions_to_dict(score.contributions, top=top),
    }


def rejection_to_dict(rejection: RowRejection) -> dict:
    """Ligne refusée : rang, référence et un motif par champ en cause."""
    return {
        "index": rejection.index,
        "reference": rejection.reference,
        "errors": [{"field": e.field, "message": e.message} for e in rejection.errors],
    }


def drift_to_dict(drift_result: CampaignDrift) -> dict:
    """Bilan de dérive en JSON, valeurs `NaN` ramenées à `null`."""
    return {
        "mesurable": drift_result.mesurable,
        "motif": drift_result.motif,
        "verdict": drift_result.verdict,
        "psi_max": _clean(drift_result.psi_max),
        "variables": [
            {
                "variable": v.variable,
                "psi": _clean(v.psi),
                "ks_statistic": _clean(v.ks_statistic),
                "ks_pvalue": _clean(v.ks_pvalue),
                "shift_std": _clean(v.shift_std),
                "verdict": v.verdict,
            }
            for v in drift_result.variables
        ],
    }


def fiche_to_dict(contract: ServiceContract) -> dict:
    """La fiche publiée par `/v1/modele` : de quoi générer un formulaire et vérifier le périmètre.

    Porte les colonnes et leur typage, les modalités canoniques, les bornes et cohérences,
    le seuil par défaut, les seuils de dérive, et les **exclusions avec leur motif** — un
    intégrateur voit ainsi ce que le modèle refuse, et pourquoi, sans lire de rapport.
    """
    facts, defaults = contract.facts, contract.defaults
    return {
        "version": facts.version,
        "input_columns": list(facts.input_columns),
        "derived_columns": list(facts.derived_columns),
        "numeric": list(facts.numeric),
        "categorical": list(facts.categorical),
        "nominal_modalities": {k: list(v) for k, v in facts.nominal_modalities.items()},
        "exclusions": [{"column": e.column, "motif": e.motif} for e in facts.exclusions],
        "themes": dict(facts.themes),
        "units": {k: list(v) for k, v in facts.units.items()},
        "bounds": {
            k: {"minimum": b.minimum, "maximum": b.maximum} for k, b in defaults.bounds.items()
        },
        "coherence": [{"left": r.left, "right": r.right} for r in defaults.coherence],
        "seuil_defaut": defaults.threshold,
        "derive": {
            "surveillance": defaults.drift_surveillance,
            "alerte": defaults.drift_alerte,
            "effectif_min": defaults.drift_effectif_min,
        },
    }


def synthese(n_recus: int, n_scores: int, n_refuses: int, part_signalee: float | None) -> Mapping:
    """Synthèse d'une campagne : reçus, scorés, refusés, et part signalée si exposée."""
    return {
        "dossiers_recus": n_recus,
        "dossiers_scores": n_scores,
        "dossiers_refuses": n_refuses,
        "part_signalee": part_signalee,
    }
