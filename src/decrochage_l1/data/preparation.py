"""Mise en forme du jeu de données du cas d'usage : conformer, recoder, dédoublonner.

Module **spécifique au cas d'usage** - il porte la seule connaissance métier de la
chaîne de mise en forme : le vocabulaire cible (`CANONICAL_MODALITIES`). Le reste
est délégué aux briques agnostiques de `data.utils` (mesure, primitives, mécanisme
de recodage) : ce module les **orchestre**, il ne les réécrit pas.

`transform` applique les **trois règles**, et rien d'autre —

- **conformer les écritures** (`conform`) : les nombres deviennent des nombres, les
  dates des dates, les textes une forme de comparaison. Une écriture change, jamais
  une information : `"12,0"` et `"12.0 km"` disaient déjà la même chose ;
- **recoder le vocabulaire** (`recoding_utils.recode` + `CANONICAL_MODALITIES`) :
  `f` et `femme` sont le même mot. Ramener des synonymes à une forme unique ne retire
  aucune valeur - cela cesse d'en compter une pour plusieurs ;
- **retirer les lignes strictement identiques** : une ligne dont toutes les colonnes
  répètent celles d'une autre ne porte rien que sa jumelle ne porte déjà.

Ce qui n'y est **pas** : aucun manquant imputé, aucune colonne retirée - pas même
celles à variance nulle -, aucun encodage numérique, aucune jointure. Ces décisions
se constatent à l'EDA et s'appliquent au palier gold.

**`transform` sert deux fois**, et c'est sa raison d'être : le notebook l'appelle en
§5 pour rendre le jeu explorable - le résultat y est un *jeu de travail*, jetable,
qui ne sort pas de la section - puis en §7 pour fabriquer le palier. Mêmes règles,
mêmes sorties : ce qui a été exploré est bien ce qui est préparé.

**L'ordre des trois opérations n'est pas indifférent.** Le dédoublonnage vient en
dernier : deux lignes qui ne différaient que par la casse, ou qui portaient `f` d'un
côté et `femme` de l'autre, ne deviennent des jumelles qu'une fois l'écriture et le
vocabulaire unifiés.

`build_gold` fabrique ensuite le **palier gold** à partir du silver : elle retire les
colonnes exclues *par principe* (liste déclarée et justifiée dans le notebook, passée
en paramètre) et dérive quelques features ligne à ligne. C'est la seule étape de ce
module qui **retire** des colonnes ; le silver, lui, n'en perd aucune.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from decrochage_l1.data.utils import cleaning_utils as cleaning
from decrochage_l1.data.utils import profiling_utils, recoding_utils

# Forme canonique -> écritures normalisées qu'elle absorbe. Cette orientation est
# celle qui se relit : on voit le groupe, pas une liste de correspondances plates.
# Deux choix ne vont pas de soi : `autre` et `non renseigné` ne fusionnent pas, parce
# que `nb`/`autre` sont des identités déclarées quand `nr` est une absence de réponse ;
# `boursier` reste `oui`/`non` en texte, parce que le passer en 0/1 serait un
# encodage de variable, et l'encodage relève du `Pipeline`, pas du recodage.
# Les colonnes absentes d'ici (`filiere`, `etablissement_origine`) n'ont aucun
# synonyme : uniformiser leur écriture suffit à les ramener à leurs modalités.
CANONICAL_MODALITIES: recoding_utils.Vocabulary = {
    "sexe": {
        "femme": ("f", "femme"),
        "homme": ("h", "m", "homme"),
        "autre": ("nb", "autre"),
        "non renseigné": ("nr",),
    },
    "bac_type": {
        "general": ("gen", "general", "generale"),
        "technologique": ("techno", "technologique"),
        "professionnel": ("pro", "professionnel"),
    },
    "mention_bac": {
        "passable": ("p", "passable"),
        "assez bien": ("ab", "assez bien"),
        "bien": ("b", "bien"),
        "tres bien": ("tb", "tres bien"),
    },
    "boursier": {
        "oui": ("o", "oui", "1"),
        "non": ("n", "non", "0"),
    },
}


@dataclass(frozen=True)
class TransformResult:
    """Effet de la transformation - les faits à afficher, sans référence au disque."""

    n_rows_source: int
    n_duplicates_removed: int
    n_columns: int
    recoded_columns: tuple[str, ...]

    @property
    def n_rows(self) -> int:
        """Lignes restantes une fois les doublons exacts retirés."""
        return self.n_rows_source - self.n_duplicates_removed


def conform(data: pd.DataFrame, profile: pd.DataFrame) -> pd.DataFrame:
    """Uniformise l'**écriture** des valeurs, en s'appuyant sur le type déduit au profil.

    Colonne par colonne : les nombres sont lus en nombres (virgule décimale et unité
    collée comprises), les dates en dates (tous formats rencontrés), les textes ramenés
    à une forme de comparaison (minuscules, sans accent, espaces normalisés). Sans ce
    typage, une colonne restée en texte n'a ni distribution, ni quantile, ni corrélation.

    Aucune modalité n'est fusionnée, aucune ligne ni colonne supprimée, aucun manquant
    imputé : c'est une mise en forme, réversible en information.
    """
    semantic_types = profile.set_index("colonne")["type_semantique"].to_dict()
    result = data.copy()

    for column in result.columns:
        # Les cellules vides deviennent des manquants explicites : sinon une colonne
        # textuelle garderait une modalité « chaîne vide », comptée comme une catégorie
        # à part entière dans toute exploration.
        values = cleaning.blank_to_na(result[column])
        match semantic_types.get(column):
            case "entier":
                # `Int64` (entier *nullable*) et non `int64` : une colonne entière
                # comportant des manquants basculerait en flottant - « 3 » deviendrait
                # « 3.0 », illisible dans un histogramme comme dans un tableau.
                units = profiling_utils.detect_units(values)
                result[column] = cleaning.parse_number(values, units).astype("Int64")
            case "decimal":
                result[column] = cleaning.parse_number(values, profiling_utils.detect_units(values))
            case "date":
                formats = profiling_utils.detect_date_formats(values)
                result[column] = cleaning.parse_date(values, formats)
            case "booleen":
                # Un booléen déjà écrit 0/1 se type en nombre - aucune convention à
                # choisir. Écrit en toutes lettres (« Oui », « N »), il exigerait de
                # décider laquelle des deux modalités vaut 1 : c'est un recodage, il
                # n'appartient pas à la mise en forme.
                numbers = cleaning.parse_number(values)
                already_numeric = numbers.notna().sum() == values.notna().sum()
                result[column] = (
                    numbers.astype("Int64") if already_numeric else cleaning.normalize_text(values)
                )
            case _:
                result[column] = cleaning.normalize_text(values)

    return result


def transform(
    data: pd.DataFrame,
    profile: pd.DataFrame,
    vocabulary: recoding_utils.Vocabulary | None = None,
) -> tuple[pd.DataFrame, TransformResult]:
    """Conforme, recode, dédoublonne - les trois règles du silver, **sans écriture disque**.

    Le profil est **passé**, non recalculé : la conformation est pilotée par la mesure
    (le type sémantique déduit colonne par colonne). Le `vocabulary` par défaut est
    celui du cas d'usage (`CANONICAL_MODALITIES`), injecté dans le mécanisme agnostique
    de `recoding_utils`.
    """
    vocabulary = CANONICAL_MODALITIES if vocabulary is None else vocabulary

    conformed = conform(data, profile)
    recoded, recoded_columns = recoding_utils.recode(conformed, vocabulary)
    deduplicated = recoded.drop_duplicates().reset_index(drop=True)

    return deduplicated, TransformResult(
        n_rows_source=len(conformed),
        n_duplicates_removed=len(conformed) - len(deduplicated),
        n_columns=deduplicated.shape[1],
        recoded_columns=recoded_columns,
    )


@dataclass(frozen=True)
class GoldResult:
    """Effet du passage silver → gold - les faits à afficher, sans référence au disque."""

    n_rows: int
    n_columns: int
    dropped: tuple[str, ...]
    derived: tuple[str, ...]


def build_gold(
    silver: pd.DataFrame, drop_columns: Sequence[str]
) -> tuple[pd.DataFrame, GoldResult]:
    """Applique les exclusions de principe et dérive les features ligne à ligne - le gold.

    `drop_columns` - identifiants, fuites de fin de S1, variance nulle - est **déclaré
    dans le notebook**, avec la décision qui fonde chaque retrait, et passé ici : le
    module applique, il ne juge pas (aucune table de motifs dans le code). Les cibles
    n'y figurent pas - le gold les conserve pour l'entraînement (le split X/y est en §9).

    Deux features déterministes, calculées ligne à ligne et rapportées au **même**
    dénominateur pour rester comparables d'un étudiant à l'autre :

    - `taux_rendu`    = `nb_devoirs_rendus` / `nb_devoirs_total` ;
    - `ratio_retards` = `retards_rendus`   / `nb_devoirs_total`.

    Le dénominateur est le nombre de devoirs **attendus** (`nb_devoirs_total`), non le
    nombre **rendus** : rapporté aux rendus, un unique devoir rendu en retard vaudrait
    100 % - un artefact de faible base (justification au journal §7).
    """
    gold = silver.drop(columns=list(drop_columns))

    # Division sûre : NaN là où le dénominateur manque ou vaut 0 - aucun cas dans le jeu
    # reçu (min = 8), mais le garde-fou évite un `inf` si la source venait à changer.
    denominator = gold["nb_devoirs_total"].where(gold["nb_devoirs_total"] > 0)
    gold["taux_rendu"] = gold["nb_devoirs_rendus"] / denominator
    gold["ratio_retards"] = gold["retards_rendus"] / denominator

    return gold, GoldResult(
        n_rows=len(gold),
        n_columns=gold.shape[1],
        dropped=tuple(drop_columns),
        derived=("taux_rendu", "ratio_retards"),
    )
