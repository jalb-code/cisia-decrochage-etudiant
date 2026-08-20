"""Spécification figée du pipeline — les jugements éprouvés, transcrits en config (D44).

Ce module ne **décide** rien : il **relit** les jugements que le notebook a déclarés et
défendus (exclusions du gold, rôles de colonnes, features minimisées, cible, seed,
hyperparamètres retenus, politique de seuil, seuils de dérive, gouvernance de la fiche).
Industrialiser, c'est transcrire ces choix décrits au notebook vers un fichier de
configuration versionné (`configs/pipeline_spec.json`), que la CLI relit pour rejouer la
chaîne à iso-périmètre — sans jamais rejouer l'optimisation des hyperparamètres, qui reste
l'affaire du notebook (§9).

`PipelineSpec` porte les **valeurs** ; le *pourquoi* de chacune vit au journal de bord du
notebook, pas ici. Une modalité absente d'un jeu neuf ne peut pas faire disparaître sa
colonne : le vocabulaire catégoriel reste déclaré dans `data.preparation`, jamais déduit.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

# Racine du dépôt, déduite de l'emplacement du package : …/src/decrochage_l1/modeling/spec.py.
# Indépendante de `DECROCHAGE_L1_ROOT_DIR` (qui n'isole que les données) - la spec est un
# fichier de configuration versionné du dépôt, pas une donnée d'exécution.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def default_spec_path() -> Path:
    """Chemin de la spec versionnée (`configs/pipeline_spec.json`), ancré à la racine du dépôt."""
    return _REPO_ROOT / "configs" / "pipeline_spec.json"


@dataclass(frozen=True)
class PipelineSpec:
    """Jugements figés que la CLI rejoue — transcription des décisions défendues au notebook."""

    version: str
    seed: int
    test_size: float
    n_splits: int
    target: str
    target_secondary: str
    source_file: str
    gold_exclusions: list[str]
    protected: list[str]
    matrix_excluded: list[str]
    numeric_columns: list[str]
    ordinal: list[str]
    nominal: list[str]
    ablation_removed: list[str]
    family_classifier: str
    family_regressor: str
    hyperparams_classifier: dict
    recall_target: float
    drift_defaults: dict
    themes: dict[str, str]
    model_card: dict = field(repr=False)

    def feature_roles(self, columns: list[str]) -> tuple[list[str], list[str], list[str]]:
        """Déduit (numériques, ordinales, nominales) des colonnes du gold, comme le notebook (§8).

        Les cibles, les variables protégées et les exclusions de matrice sortent ; ce qui reste,
        hors ordinales/nominales déclarées, est numérique. Le calcul est **déclaré, pas déduit
        du contenu** : les rôles viennent de la spec, seul l'inventaire des numériques suit les
        colonnes présentes.
        """
        reserved = {
            self.target,
            self.target_secondary,
            *self.protected,
            *self.matrix_excluded,
            *self.ordinal,
            *self.nominal,
        }
        numeric = [c for c in columns if c not in reserved]
        ordinal = [c for c in self.ordinal if c in columns]
        nominal = [c for c in self.nominal if c in columns]
        return numeric, ordinal, nominal

    def features_min(self, columns: list[str]) -> list[str]:
        """Jeu de features minimisé : toutes les features, moins les blocs retirés par ablation."""
        numeric, ordinal, nominal = self.feature_roles(columns)
        features = numeric + ordinal + nominal
        removed = set(self.ablation_removed)
        return [f for f in features if f not in removed]


def load_spec(path: Path | None = None) -> PipelineSpec:
    """Charge la spec depuis le JSON versionné (défaut : `configs/pipeline_spec.json`)."""
    path = path or default_spec_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PipelineSpec(
        version=raw["version"],
        seed=raw["seed"],
        test_size=raw["test_size"],
        n_splits=raw["n_splits"],
        target=raw["target"],
        target_secondary=raw["target_secondary"],
        source_file=raw["source_file"],
        gold_exclusions=raw["gold_exclusions"],
        protected=raw["protected"],
        matrix_excluded=raw["matrix_excluded"],
        numeric_columns=raw["numeric_columns"],
        ordinal=raw["roles"]["ordinal"],
        nominal=raw["roles"]["nominal"],
        ablation_removed=raw["ablation_removed"],
        family_classifier=raw["family_classifier"],
        family_regressor=raw["family_regressor"],
        hyperparams_classifier=raw["hyperparams_classifier"],
        recall_target=raw["threshold_policy"]["recall_target"],
        drift_defaults=raw["drift_defaults"],
        themes=raw["themes"],
        model_card=raw["model_card"],
    )
