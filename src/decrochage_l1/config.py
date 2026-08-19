"""Configuration **runtime** du projet — où lire, où écrire, surchargeable par l'environnement.

Ce module ne dit rien de ce que *sont* les données : ni colonne, ni modalité, ni
borne. Il ne porte que des réglages d'exécution — *où* et *comment* on tourne.

Chaque réglage se surcharge sans toucher au code, via une variable d'environnement
préfixée `DECROCHAGE_L1_` ou un fichier `.env` (pratique « 12-factor ») — par
exemple `DECROCHAGE_L1_ROOT_DIR=/tmp/essai`. Les chemins dérivent tous de
`root_dir`, déduit de l'emplacement du package et donc indépendant du répertoire
courant : un notebook lancé depuis `notebooks/` et un test lancé depuis la racine
visent les mêmes fichiers.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]  # …/src/decrochage_l1/config.py -> racine du dépôt


class Settings(BaseSettings):
    """Réglages d'exécution, typés et surchargeables par l'environnement (`DECROCHAGE_L1_*`)."""

    model_config = SettingsConfigDict(
        env_prefix="DECROCHAGE_L1_",
        env_file=".env",
        extra="ignore",
    )

    # Seule racine surchargée directement ; tous les sous-dossiers en dérivent.
    root_dir: Path = _ROOT

    @property
    def data_dir(self) -> Path:
        """Dossier racine des données (`data/`)."""
        return self.root_dir / "data"

    @property
    def raw_dir(self) -> Path:
        """Sources brutes déposées à la main — zone de dépôt, jamais modifiée."""
        return self.data_dir / "raw"

    @property
    def sample_dir(self) -> Path:
        """Échantillon déposé à la main pour la première lecture — jamais modifié."""
        return self.data_dir / "sample"

    # Les trois paliers ci-dessous sont tous PRODUITS par le code, jamais déposés à
    # la main, et tous en §7 : la chaîne repart des fichiers reçus, pas du jeu de
    # travail. Chacun n'entre qu'une transformation supplémentaire, pour qu'une
    # anomalie constatée en aval se rattache à un palier — donc à une étape — précis.

    @property
    def bronze_dir(self) -> Path:
        """Palier bronze : copie exacte des fichiers reçus, immuable — rien n'y est transformé."""
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        """Palier silver : écritures conformées, vocabulaire recodé, doublons exacts retirés."""
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        """Palier gold : décisions de l'EDA appliquées — jeu de référence, lisible tel quel."""
        return self.data_dir / "gold"

    @property
    def report_dir(self) -> Path:
        """Rapports générés (profilage HTML) — hors dépôt : ils citent des valeurs brutes."""
        return self.root_dir / "reports"

    @property
    def models_dir(self) -> Path:
        """Artefacts modèle sérialisés (§10) — produits par le code, hors dépôt.

        Y sont figés les pipelines déployés (`abandon`, `moyenne_finale`) et la fiche
        d'identité qui les accompagne. Rien n'y est déposé à la main : le notebook les
        écrit au §10, le service d'inférence les relit.
        """
        return self.root_dir / "models"


# Instance partagée, importable partout : `from decrochage_l1.config import settings`.
settings = Settings()
