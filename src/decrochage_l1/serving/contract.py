"""La fiche du modèle : le descripteur de service, produit par le notebook (§10).

Le **contrat d'entrée** (colonnes, types, bornes, modalités) vit dans le schéma Pydantic de
l'API (`schemas.PredictEtudiantForm`) ; la fiche porte ce qu'un schéma d'entrée ne sait pas
exprimer :

- **Faits du modèle** (`ModelFacts`) — version, typage num/catégoriel (sélection des colonnes
  de dérive), thèmes d'explicabilité, distribution de référence pour la dérive. Les changer,
  c'est un **autre modèle** : ils sont figés avec l'artefact.
- **Paramètres d'exploitation** (`OperationalDefaults`) — seuil de décision et seuils de
  dérive. Leur **défaut** vit ici (déclaré au notebook, défendu à l'oral) ; l'exploitation
  peut les **surcharger par configuration**, sans réentraîner ni resérialiser.

Le module porte les **structures** et leur cohérence, pas les valeurs : thèmes, seuil et
bornes de dérive sont déclarés au notebook et injectés à la construction. Aucune table de
jugement codée ici.
"""

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def build_drift_reference(frame: pd.DataFrame, *, seed: int) -> pd.DataFrame:
    """Référence de dérive dé-identifiée : chaque colonne mélangée indépendamment (D45).

    La mesure de dérive ne lit que la **marginale** de chaque variable (PSI par bacs, KS,
    proportions catégorielles) - la structure jointe des lignes ne lui sert jamais. On permute
    donc chaque colonne avec la même graine : les distributions par variable restent **intactes**
    (PSI et KS inchangés au bit près), mais plus aucune ligne ne correspond à un dossier réel -
    aucun étudiant n'est reconstituable (minimisation, art. 5.1.c). La graine fixe rend la
    référence reproductible ; chaque colonne reçoit sa propre permutation (l'état du générateur
    avance d'un tirage à l'autre).
    """
    rng = np.random.default_rng(seed)
    melangees = {
        colonne: frame[colonne].to_numpy()[rng.permutation(len(frame))] for colonne in frame.columns
    }
    return pd.DataFrame(melangees, columns=frame.columns)


@dataclass
class ModelFacts:
    """Faits structurels du modèle entraîné — figés avec l'artefact (immuables en prod)."""

    version: str
    numeric: tuple[str, ...]  # colonnes numériques, pour la sélection des variables de dérive
    categorical: tuple[str, ...]  # colonnes catégorielles, idem
    themes: dict[str, str]  # variable source -> thème, pour l'agrégation de l'explicabilité
    # Référence de dérive : marginales par colonne, mélangées indépendamment (D45) ; hors repr.
    drift_reference: pd.DataFrame | None = field(default=None, compare=False, repr=False)
    # Atteste que `drift_reference` porte des marginales dé-identifiées, pas des dossiers (D45).
    drift_reference_shuffled: bool = False


@dataclass
class OperationalDefaults:
    """Paramètres d'exploitation — défaut déclaré ici, surchargeable par configuration (D38)."""

    threshold: float
    drift_surveillance: float
    drift_alerte: float
    drift_effectif_min: int


@dataclass
class ServiceContract:
    """Fiche complète : faits du modèle + défauts d'exploitation, sérialisée avec l'artefact."""

    facts: ModelFacts
    defaults: OperationalDefaults

    def validate(self) -> None:
        """Contrôle la cohérence interne de la fiche ; lève `ValueError` au premier défaut.

        Garde-fou de construction : le seuil est une probabilité et les seuils de dérive sont
        ordonnés. On échoue à l'écriture de la fiche, pas au premier appel en production.
        """
        if not 0.0 <= self.defaults.threshold <= 1.0:
            raise ValueError(f"seuil hors [0, 1] : {self.defaults.threshold}")

        if not 0.0 <= self.defaults.drift_surveillance <= self.defaults.drift_alerte:
            raise ValueError(
                "seuils de dérive non ordonnés : "
                f"surveillance={self.defaults.drift_surveillance}, "
                f"alerte={self.defaults.drift_alerte}"
            )

        if self.defaults.drift_effectif_min <= 0:
            raise ValueError(f"effectif minimal non positif : {self.defaults.drift_effectif_min}")


def save(contract: ServiceContract, path: Path) -> None:
    """Sérialise la fiche (joblib), après en avoir vérifié la cohérence."""
    contract.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(contract, path)


def load(path: Path) -> ServiceContract:
    """Recharge une fiche sérialisée. La cohérence a été garantie à l'écriture."""
    return joblib.load(path)
