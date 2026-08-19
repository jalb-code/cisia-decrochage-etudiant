"""La fiche du modèle : le contrat que le service lit, produit par le notebook (§10).

Elle sépare deux natures de valeurs (D38) :

- **Faits du modèle entraîné** (`ModelFacts`) — liste et typage des colonnes, modalités
  canoniques, exclusions motivées, thèmes, distribution de référence pour la dérive. Les
  changer, c'est un **autre modèle** : ils sont figés avec l'artefact.
- **Paramètres d'exploitation** (`OperationalDefaults`) — seuil de décision, bornes de
  plausibilité, cohérences, seuils de dérive. Leur **défaut** vit ici (déclaré au notebook,
  défendu à l'oral) ; l'exploitation peut les **surcharger par configuration**, sans
  réentraîner ni resérialiser.

Le module porte les **structures** et leur cohérence, pas les valeurs : celles-ci sont
déclarées au notebook et injectées à la construction. Aucune table de jugement codée ici.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import pandas as pd


@dataclass(frozen=True)
class Exclusion:
    """Colonne écartée du périmètre de scoring, avec le motif publié par `/v1/modele`."""

    column: str
    motif: str


@dataclass(frozen=True)
class Bound:
    """Borne de plausibilité d'un champ numérique — minimum et maximum, chacun facultatif.

    Une grandeur ouverte (distance, volume horaire) se déclare sans `maximum` : on ne
    rejette pas demain une valeur légitime inédite au nom d'un plafond arbitraire.
    """

    minimum: float | None = None
    maximum: float | None = None

    def contains(self, value: float) -> bool:
        """Vrai si `value` respecte les bornes déclarées (côté absent = non contraint)."""
        if self.minimum is not None and value < self.minimum:
            return False
        return not (self.maximum is not None and value > self.maximum)


@dataclass(frozen=True)
class CoherenceRule:
    """Inégalité attendue entre deux champs : `left` ≤ `right`, bornes incluses."""

    left: str
    right: str

    def holds(self, row: Mapping) -> bool:
        """Vrai si la règle tient ; un champ manquant ne l'infirme pas (rien à comparer)."""
        left_value, right_value = row.get(self.left), row.get(self.right)
        if left_value is None or right_value is None:
            return True
        return left_value <= right_value


@dataclass
class ModelFacts:
    """Faits structurels du modèle entraîné — figés avec l'artefact (immuables en prod)."""

    version: str
    input_columns: tuple[str, ...]  # ce que l'appelant transmet (collecté, à mi-parcours du S1)
    derived_columns: tuple[str, ...]  # calculées par le service, jamais reçues (anti-divergence)
    numeric: tuple[str, ...]
    categorical: tuple[str, ...]
    nominal_modalities: dict[str, tuple[str, ...]]
    exclusions: tuple[Exclusion, ...]
    themes: dict[str, str]  # variable source -> thème, pour l'agrégation de l'explicabilité
    # Unités à retirer à la conversion d'un champ numérique (« % », « km »…). Déclarées au
    # notebook — la même information que `detect_units` mesure côté préparation —, jamais
    # devinées par le service : c'est ce qui lui fait conformer une entrée à l'identique.
    units: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Instantané du train, servant de référence à la dérive ; hors comparaison/repr (volumineux).
    drift_reference: pd.DataFrame | None = field(default=None, compare=False, repr=False)


@dataclass
class OperationalDefaults:
    """Paramètres d'exploitation — défaut déclaré ici, surchargeable par configuration (D38)."""

    threshold: float
    bounds: dict[str, Bound]
    coherence: tuple[CoherenceRule, ...]
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

        Garde-fou de construction : bornes, cohérences et thèmes ne peuvent porter que sur
        des colonnes connues, le seuil est une probabilité, et les seuils de dérive sont
        ordonnés. On échoue à l'écriture de la fiche, pas au premier appel en production.
        """
        known = set(self.facts.input_columns) | set(self.facts.derived_columns)

        unknown_bounds = set(self.defaults.bounds) - known
        if unknown_bounds:
            raise ValueError(f"bornes sur des colonnes inconnues : {sorted(unknown_bounds)}")

        for rule in self.defaults.coherence:
            missing = {rule.left, rule.right} - known
            if missing:
                raise ValueError(f"cohérence sur des colonnes inconnues : {sorted(missing)}")

        unknown_themes = set(self.facts.themes) - known
        if unknown_themes:
            raise ValueError(f"thèmes sur des colonnes inconnues : {sorted(unknown_themes)}")

        typed = set(self.facts.numeric) | set(self.facts.categorical)
        unknown_typed = typed - known
        if unknown_typed:
            raise ValueError(f"typage sur des colonnes inconnues : {sorted(unknown_typed)}")

        non_numeric_units = set(self.facts.units) - set(self.facts.numeric)
        if non_numeric_units:
            raise ValueError(
                f"unités sur des colonnes non numériques : {sorted(non_numeric_units)}"
            )

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
