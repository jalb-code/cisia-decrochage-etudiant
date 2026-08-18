"""Réglages d'EXPLOITATION du service — surchargent la fiche par l'environnement (D38).

Ce que porte la fiche est un défaut défendu au notebook ; ce module lit ce que l'exploitation
décide sans resérialiser : clés d'API, seuil effectif, exposition de l'indicateur, origines
CORS, activation des métriques. Rien de ce qui touche au modèle lui-même n'est ici.

Aucune clé d'API par défaut : sans `DECROCHAGE_API_KEYS`, les routes protégées répondent 503.
Un contrôle d'accès qui se contourne par une clé connue n'est pas un contrôle.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Réglages runtime du service, surchargeables par variables d'environnement `DECROCHAGE_*`."""

    model_config = SettingsConfigDict(env_prefix="DECROCHAGE_", env_file=".env", extra="ignore")

    api_keys: str = ""  # clés autorisées, séparées par des virgules ; vide => routes en 503
    exposer_indicateur: bool = False  # exposer « Risque / Non » en plus de la probabilité
    seuil_defaut: float | None = None  # surcharge du seuil de la fiche ; None => celui de la fiche
    cors_origins: str = ""  # origines autorisées pour le navigateur, séparées par des virgules
    monitoring_actif: bool = True  # exposer /metrics

    @property
    def allowed_keys(self) -> set[str]:
        """Ensemble des clés d'API autorisées ; vide signifie « contrôle non configuré »."""
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}

    @property
    def origins(self) -> list[str]:
        """Origines CORS autorisées ; vide signifie « aucun appel navigateur autorisé »."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
