"""Orchestration du scoring : de lignes validées aux résultats, sur les deux modèles.

Assemble ce que le service sait faire — probabilité d'`abandon`, note `moyenne_finale`
estimée, contributions explicatives, dérive de campagne — à partir d'un `Bundle` chargé et
d'un lot **déjà validé** (schéma `schemas.PredictEtudiantForm`) et **conformé** (dérivées
ajoutées par `normalization.add_derived`). Le calcul est **groupé** : une seule prédiction
vectorisée par modèle, une seule passe d'explicabilité.

Le seuil de décision est **passé** (défaut de la fiche ou surcharge d'exploitation) ; la
sortie secondaire est **bornée [0 ; 20]** (le régresseur linéaire peut extrapoler au-delà) ;
l'indicateur « signalé » n'est calculé que si l'exploitation choisit de l'exposer.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from decrochage_l1.serving import drift, explain
from decrochage_l1.serving.explain import Contributions
from decrochage_l1.serving.store import Bundle

MOYENNE_MIN, MOYENNE_MAX = 0.0, 20.0


@dataclass(frozen=True)
class DossierScore:
    """Résultat d'un dossier : probabilité, note estimée, indicateur et explicabilité."""

    reference: str | None
    probability: float
    moyenne_finale: float
    signaled: bool | None  # None quand l'indicateur n'est pas exposé (probabilité seule)
    contributions: Contributions


def _model_features(bundle: Bundle) -> list[str]:
    """Colonnes attendues par le modèle, dans l'ordre de son entraînement."""
    return list(bundle.classifier.feature_names_in_)


def capacity_threshold(bundle: Bundle, accepted: pd.DataFrame, capacite: int) -> float:
    """Seuil qui signale au plus `capacite` dossiers : la capacité-ème plus forte probabilité.

    Le seuil est **relatif à la cohorte** : on trie les probabilités décroissantes et on coupe
    au rang `capacite`. Cohorte plus petite que la capacité renvoie un seuil 0 (tout le monde
    tient), cohorte vide un seuil 1 (rien à signaler). Des probabilités ex æquo au rang de coupe
    peuvent signaler un peu plus que `capacite` : on préfère inclure que départager au hasard.
    """
    if len(accepted) == 0:
        return 1.0
    features = accepted[_model_features(bundle)]
    probabilities = bundle.classifier.predict_proba(features)[:, 1]
    if capacite >= len(probabilities):
        return 0.0
    ranked = np.sort(probabilities)[::-1]
    return float(ranked[capacite - 1])


def score(
    bundle: Bundle,
    accepted: pd.DataFrame,
    references: list[str | None],
    *,
    threshold: float | None,
    expose_indicator: bool,
) -> list[DossierScore]:
    """Score un lot conformé : probabilité, note bornée, indicateur optionnel, contributions.

    `accepted` porte au moins les colonnes du modèle (issues de la validation) ; on les
    sélectionne dans l'ordre attendu avant prédiction. Rien n'est réordonné en sortie : les
    résultats reviennent dans l'ordre reçu — ordonner par risque serait produire une liste de
    priorités, ce que le dispositif laisse à l'équipe pédagogique.
    """
    if len(accepted) == 0:
        return []

    features = accepted[_model_features(bundle)]
    probability = bundle.classifier.predict_proba(features)[:, 1]
    moyenne = np.clip(bundle.regressor.predict(features), MOYENNE_MIN, MOYENNE_MAX)
    contributions = explain.batch_contributions(
        bundle.classifier, features, themes=bundle.contract.facts.themes
    )

    return [
        DossierScore(
            reference=references[i],
            probability=float(probability[i]),
            moyenne_finale=float(moyenne[i]),
            signaled=bool(probability[i] >= threshold) if expose_indicator else None,
            contributions=contributions[i],
        )
        for i in range(len(accepted))
    ]


def assess_drift(
    bundle: Bundle,
    accepted: pd.DataFrame,
    *,
    seuil_surveillance: float,
    seuil_alerte: float,
    effectif_min: int,
) -> drift.CampaignDrift:
    """Mesure la dérive du lot contre la distribution de référence de la fiche.

    Sans référence embarquée, la dérive est déclarée non mesurable — les prédictions restent
    servies : refuser de scorer parce que la surveillance manque punirait la campagne pour un
    défaut d'outillage. Les seuils et l'effectif minimal sont **passés** (défaut de la fiche,
    surchargeable par l'exploitation), jamais lus ici : le module porte la mesure, pas la politique.
    """
    facts = bundle.contract.facts
    reference = facts.drift_reference
    if reference is None:
        return drift.CampaignDrift(
            mesurable=False,
            motif="aucune distribution de référence dans la fiche",
            variables=(),
            psi_max=float("nan"),
            verdict=drift.STABLE,
        )

    numeric = [c for c in facts.numeric if c in accepted.columns and c in reference.columns]
    categorical = [c for c in facts.categorical if c in accepted.columns and c in reference.columns]
    return drift.assess(
        reference,
        accepted,
        numeric=numeric,
        categorical=categorical,
        seuil_surveillance=seuil_surveillance,
        seuil_alerte=seuil_alerte,
        effectif_min=effectif_min,
    )
