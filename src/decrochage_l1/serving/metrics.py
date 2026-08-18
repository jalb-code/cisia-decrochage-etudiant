"""Métriques métier du service — ce que l'instrumentation générique ne rend pas visible.

Le collecteur générique fournit trafic, codes de retour et durées par route. Trois
indicateurs n'en découlent pas et sont donc exposés ici :

- **modèle chargé** — distingue « le processus répond » de « le processus peut prédire ».
  Un service démarré sans artefact répond 200 sur `/health` ; sans cette jauge, la
  surveillance ne verrait aucun incident alors qu'aucune prédiction n'est produite ;
- **seuil appliqué** — rend la politique de décision observable : on constate qu'un
  déploiement n'applique pas le seuil attendu ;
- **refus de périmètre par colonne** — compte les envois d'une variable interdite. Ce n'est
  pas une défaillance du service mais un incident de contrat côté appelant.

Les séries du compteur sont **créées à zéro au démarrage**, une par colonne interdite : sans
cette initialisation, une règle d'alerte en `increase(...)` resterait muette (le collecteur
ne verrait jamais le passage de 0 à 1). Aucune métrique ne porte d'étiquette identifiante.
"""

from collections.abc import Iterable

from prometheus_client import Counter, Gauge

from decrochage_l1.serving.validation import RowRejection

MODEL_LOADED = Gauge("decrochage_modele_charge", "1 si un modèle utilisable est chargé, 0 sinon")
DECISION_THRESHOLD = Gauge(
    "decrochage_seuil_defaut", "Seuil de décision effectif appliqué par le service"
)
# Le suffixe `_total` est ajouté par Prometheus : la série exposée est
# `decrochage_refus_perimetre_total`.
PERIMETER_REFUSALS = Counter(
    "decrochage_refus_perimetre",
    "Nombre d'envois d'une variable hors périmètre, par colonne",
    ["colonne"],
)


def set_model_loaded(loaded: bool) -> None:
    """Reflète la disponibilité du modèle (1 utilisable, 0 sinon)."""
    MODEL_LOADED.set(1 if loaded else 0)


def set_threshold(value: float) -> None:
    """Publie le seuil de décision effectif, pour le rendre observable."""
    DECISION_THRESHOLD.set(value)


def init_perimeter_series(columns: Iterable[str]) -> None:
    """Crée à zéro une série de refus par colonne interdite, pour que les alertes se déclenchent."""
    for column in columns:
        PERIMETER_REFUSALS.labels(colonne=column)


def observe_refusals(rejections: Iterable[RowRejection], forbidden: set[str]) -> None:
    """Incrémente le compteur pour chaque envoi d'une colonne interdite connue de la fiche.

    On ne compte que les colonnes **déclarées interdites** (cardinalité bornée) : compter une
    clé arbitraire ferait exploser le nombre de séries et exposerait l'imagination de l'appelant.
    """
    for rejection in rejections:
        for error in rejection.errors:
            if error.field in forbidden:
                PERIMETER_REFUSALS.labels(colonne=error.field).inc()
