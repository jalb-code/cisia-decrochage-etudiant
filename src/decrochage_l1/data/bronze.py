"""Production du palier **bronze** : conformation, recodage, doublons exacts retirés.

Le bronze est le premier palier produit par le code (les chemins vivent dans
`config.py`). Son contrat : **aucune information n'est perdue**. Trois opérations
seulement, et rien d'autre —

- **conformer les écritures** (délégué à `profiling.conform`) : les nombres
  deviennent des nombres, les dates des dates, les textes une forme de
  comparaison. Une écriture change, jamais une information : `"12,0"` et
  `"12.0 km"` disaient déjà la même chose ;
- **recoder le vocabulaire** (piloté par `schema`) : `f` et `femme` sont le même
  mot, `gen` et `general` le même bac. Ramener des synonymes à une forme unique
  ne retire aucune valeur — cela cesse d'en compter une pour plusieurs ;
- **retirer les lignes strictement identiques** : une ligne dont toutes les
  colonnes répètent celles d'une autre ne porte rien que sa jumelle ne porte
  déjà.

Ce qui n'y est **pas** : aucun manquant imputé, aucune colonne retirée — pas même
celles à variance nulle —, aucun encodage numérique, aucune jointure, aucune
ligne porteuse d'information supprimée. Ces décisions-là se constatent à l'EDA et
s'appliquent au palier silver.

**L'ordre des trois opérations n'est pas indifférent.** Le dédoublonnage vient en
dernier : deux lignes qui ne différaient que par la casse, ou qui portaient `f`
d'un côté et `femme` de l'autre, ne deviennent des jumelles qu'une fois l'écriture
et le vocabulaire unifiés.

Le fichier écrit est une **copie de contrôle** — inspectable dans un tableur,
point de reprise pour un pipeline. Ce n'est pas ce que consomme l'exploration :
`build` rend le DataFrame, et c'est lui qui circule d'une section à l'autre. Un
CSV relu par `pandas` ne rendrait ni les dates, ni les entiers *nullable* posés
par la conformation ; le retrouver demanderait de reprofiler le fichier.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from decrochage_l1 import schema
from decrochage_l1.data import profiling

# Sources du projet, par nom de palier — les fichiers bruts portent des noms à
# espaces qu'on ne retape pas à chaque appel (cf. `data/README.md`).
SOURCES: dict[str, str] = {
    "etudiants": "dataset decrochage_etudiants_complet_V5.csv",
    "catalogue": "dataset catalogue_formations_V5.csv",
}


@dataclass(frozen=True)
class BronzeResult:
    """Ce que la production a fait — les faits à afficher, non un contrôle a posteriori."""

    source: Path
    destination: Path
    n_rows_source: int
    n_duplicates_removed: int
    n_columns: int
    recoded_columns: tuple[str, ...]

    @property
    def n_rows(self) -> int:
        """Lignes effectivement écrites."""
        return self.n_rows_source - self.n_duplicates_removed


def recode(data: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Ramène les modalités synonymes à leur forme canonique (cf. `schema`).

    Ne touche qu'aux colonnes présentes **à la fois** dans le jeu et dans le
    vocabulaire cible : le même code traite les étudiants et le catalogue, sans
    savoir lequel il reçoit. Rend aussi la liste des colonnes effectivement
    recodées — un fait à afficher, pas une trace de débogage.
    """
    result = data.copy()
    recoded: list[str] = []

    for column in result.columns:
        correspondance = schema.canonical_by_variant(str(column))
        if not correspondance:
            continue
        result[column] = result[column].replace(correspondance)
        recoded.append(str(column))

    return result, tuple(recoded)


def build(profile: profiling.CsvProfile, destination: Path) -> tuple[pd.DataFrame, BronzeResult]:
    """Produit le bronze d'un fichier déjà profilé ; rend le jeu et le compte.

    Le profil est **passé**, non recalculé : la conformation est pilotée par la
    mesure (`profiling.conform` s'appuie sur le type sémantique déduit colonne par
    colonne), et le notebook affiche cette même mesure avant de produire. Une
    seule mesure, deux usages.

    Le DataFrame rendu est la sortie qui compte — le fichier écrit à `destination`
    en est la copie de contrôle.
    """
    conformed = profiling.conform(profile.data, profile.columns)
    recoded, recoded_columns = recode(conformed)
    deduplicated = recoded.drop_duplicates().reset_index(drop=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    deduplicated.to_csv(destination, index=False)

    return deduplicated, BronzeResult(
        source=profile.file.path,
        destination=destination,
        n_rows_source=len(conformed),
        n_duplicates_removed=len(conformed) - len(deduplicated),
        n_columns=deduplicated.shape[1],
        recoded_columns=recoded_columns,
    )


def summary(results: list[BronzeResult]) -> pd.DataFrame:
    """Vue tabulaire des productions, une ligne par fichier — pour l'affichage notebook."""
    return pd.DataFrame(
        [
            {
                "fichier": result.destination.name,
                "lignes_source": result.n_rows_source,
                "doublons_retires": result.n_duplicates_removed,
                "lignes_bronze": result.n_rows,
                "colonnes": result.n_columns,
                "colonnes_recodees": len(result.recoded_columns),
            }
            for result in results
        ]
    )
