"""Métriques métier du service — ce que l'instrumentation générique ne rend pas visible.

Le collecteur générique fournit trafic, codes de retour et durées par route. Deux indicateurs
n'en découlent pas et sont donc exposés ici :

- **modèle chargé** — distingue « le processus répond » de « le processus peut prédire ».
  Un service démarré sans artefact répond 200 sur `/health` ; sans cette jauge, la
  surveillance ne verrait aucun incident alors qu'aucune prédiction n'est produite ;
- **seuil appliqué** — rend la politique de décision observable : on constate qu'un
  déploiement n'applique pas le seuil attendu.

Aucune métrique ne porte d'étiquette identifiante.
"""

from prometheus_client import Gauge

MODEL_LOADED = Gauge("decrochage_modele_charge", "1 si un modèle utilisable est chargé, 0 sinon")
DECISION_THRESHOLD = Gauge(
    "decrochage_seuil_defaut", "Seuil de décision effectif appliqué par le service"
)


def set_model_loaded(loaded: bool) -> None:
    """Reflète la disponibilité du modèle (1 utilisable, 0 sinon)."""
    MODEL_LOADED.set(1 if loaded else 0)


def set_threshold(value: float) -> None:
    """Publie le seuil de décision effectif, pour le rendre observable."""
    DECISION_THRESHOLD.set(value)
