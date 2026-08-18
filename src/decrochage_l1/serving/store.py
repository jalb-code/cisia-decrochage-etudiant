"""Entrepôt du modèle : sérialise et charge l'artefact déployable (§10), une fois.

L'artefact déployable tient en trois fichiers dans `models_dir` : le pipeline `abandon`
(classification, porte la probabilité et les contributions), le pipeline `moyenne_finale`
(régression, cible secondaire), et la **fiche** qui les décrit. `save_bundle` est le point
de sérialisation qu'appelle le notebook au §10 ; `EntrepotModele` est ce que le service
charge au démarrage.

Deux garde-fous sont **vérifiés à l'exécution**, pas seulement affirmés :

- la fiche est cohérente (`validate`) — sinon on n'écrit pas l'artefact ;
- le modèle **n'attend aucune colonne interdite** — l'intersection entre les variables
  qu'il consomme et les exclusions de la fiche fait échouer le chargement, au lieu de servir
  un modèle qui fuiterait.

Un échec de chargement **n'interrompt pas** le service : l'erreur est mémorisée et la sonde
de disponibilité l'expose. Un service qui refuse de démarrer ne laisse aucune trace ; un
service qui démarre et se déclare indisponible en laisse une.
"""

from dataclasses import dataclass
from pathlib import Path

import joblib
from sklearn.pipeline import Pipeline

from decrochage_l1.serving import contract as contract_mod
from decrochage_l1.serving.contract import ServiceContract

CLASSIFIER_FILE = "classifier.joblib"
REGRESSOR_FILE = "regressor.joblib"
CONTRACT_FILE = "contract.joblib"


@dataclass(frozen=True)
class Bundle:
    """Les trois pièces de l'artefact déployable, chargées et prêtes à servir."""

    contract: ServiceContract
    classifier: Pipeline  # cible `abandon` : probabilité + contributions
    regressor: Pipeline  # cible `moyenne_finale` : note estimée /20


def _check_no_leakage(contract: ServiceContract, classifier: Pipeline) -> None:
    """Refuse un modèle qui attendrait une colonne déclarée interdite par la fiche."""
    forbidden = {exclusion.column for exclusion in contract.facts.exclusions}
    features = set(getattr(classifier, "feature_names_in_", ()))
    leak = forbidden & features
    if leak:
        raise ValueError(f"le modèle attend des colonnes interdites (fuite) : {sorted(leak)}")


def save_bundle(
    models_dir: Path,
    *,
    contract: ServiceContract,
    classifier: Pipeline,
    regressor: Pipeline,
) -> None:
    """Sérialise l'artefact déployable (§10), après avoir vérifié fiche et absence de fuite."""
    contract.validate()
    _check_no_leakage(contract, classifier)
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(classifier, models_dir / CLASSIFIER_FILE)
    joblib.dump(regressor, models_dir / REGRESSOR_FILE)
    contract_mod.save(contract, models_dir / CONTRACT_FILE)


class EntrepotModele:
    """Porte l'artefact chargé, ou l'erreur de chargement — jamais les deux à la fois.

    Le modèle est désérialisé **une seule fois** (au démarrage du service) : le refaire à
    chaque requête coûterait des centaines de millisecondes pour un résultat identique.
    """

    def __init__(self) -> None:
        self._bundle: Bundle | None = None
        self._error: str | None = None

    def load(self, models_dir: Path) -> None:
        """Charge fiche et pipelines ; en cas d'échec, mémorise le motif sans lever."""
        try:
            classifier = joblib.load(models_dir / CLASSIFIER_FILE)
            regressor = joblib.load(models_dir / REGRESSOR_FILE)
            contract = contract_mod.load(models_dir / CONTRACT_FILE)
            _check_no_leakage(contract, classifier)
            self._bundle = Bundle(contract=contract, classifier=classifier, regressor=regressor)
            self._error = None
        except Exception as exception:
            self._bundle = None
            self._error = f"{type(exception).__name__}: {exception}"

    @property
    def ready(self) -> bool:
        """Vrai si un artefact utilisable est chargé — ce que teste la sonde de disponibilité."""
        return self._bundle is not None

    @property
    def error(self) -> str | None:
        """Motif du dernier échec de chargement, ou None si le modèle est prêt."""
        return self._error

    @property
    def bundle(self) -> Bundle:
        """L'artefact chargé ; lève si le modèle n'est pas prêt (à garder derrière `ready`)."""
        if self._bundle is None:
            raise RuntimeError(f"modèle indisponible : {self._error}")
        return self._bundle
