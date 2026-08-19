"""Métriques métier du service — ce que l'instrumentation générique ne rend pas visible.

Le collecteur générique fournit trafic, codes de retour et durées par route. Trois indicateurs
n'en découlent pas et sont donc exposés ici :

- **modèle chargé** — distingue « le processus répond » de « le processus peut prédire ».
  Un service démarré sans artefact répond 200 sur `/health` ; sans cette jauge, la
  surveillance ne verrait aucun incident alors qu'aucune prédiction n'est produite ;
- **seuil appliqué** — rend la politique de décision observable : on constate qu'un
  déploiement n'applique pas le seuil attendu ;
- **refus de périmètre par colonne** — compte les lignes refusées à la validation, imputées
  à la colonne mise en cause. Un incident de contrat côté source (extraction fautive) se lit
  colonne par colonne, sans quoi une campagne entière pourrait être rejetée en silence.

Aucune métrique ne porte d'étiquette identifiante.
"""

from collections.abc import Iterable

from prometheus_client import Counter, Gauge

MODEL_LOADED = Gauge("decrochage_modele_charge", "1 si un modèle utilisable est chargé, 0 sinon")
DECISION_THRESHOLD = Gauge(
    "decrochage_seuil_defaut", "Seuil de décision configuré (défaut de la fiche ou surcharge)"
)
# Nommé sans suffixe : le client Prometheus expose la série sous `..._total` (convention compteur).
REFUS_PERIMETRE = Counter(
    "decrochage_refus_perimetre",
    "Refus de périmètre (validation d'entrée), par colonne mise en cause",
    ["colonne"],
)


def set_model_loaded(loaded: bool) -> None:
    """Reflète la disponibilité du modèle (1 utilisable, 0 sinon)."""
    MODEL_LOADED.set(1 if loaded else 0)


def set_threshold(value: float) -> None:
    """Publie le seuil de décision effectif, pour le rendre observable."""
    DECISION_THRESHOLD.set(value)


def init_refus_series(colonnes: Iterable[str]) -> None:
    """Initialise à zéro une série de refus par colonne du contrat, au démarrage.

    Sans cette amorce, une colonne jamais refusée n'aurait aucune série et manquerait au
    tableau de bord ; on veut au contraire voir toutes les colonnes, y compris à zéro.
    """
    for colonne in colonnes:
        REFUS_PERIMETRE.labels(colonne=colonne)


def increment_refus(colonne: str) -> None:
    """Compte un refus de périmètre imputé à `colonne`."""
    REFUS_PERIMETRE.labels(colonne=colonne).inc()
