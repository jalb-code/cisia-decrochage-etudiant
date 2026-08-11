import pandas as pd
import pytest

from decrochage_l1 import schema
from decrochage_l1.config import settings
from decrochage_l1.data import bronze


def test_canonical_by_variant_inverse_la_table():
    correspondance = schema.canonical_by_variant("sexe")
    assert correspondance["f"] == "femme"
    assert correspondance["femme"] == "femme"
    assert correspondance["nr"] == "inconnu"


def test_canonical_by_variant_colonne_sans_synonyme():
    assert schema.canonical_by_variant("filiere") == {}


def test_autre_et_inconnu_ne_fusionnent_pas():
    # Une identité déclarée n'est pas une absence de réponse (cf. docstring du module).
    correspondance = schema.canonical_by_variant("sexe")
    assert correspondance["nb"] != correspondance["nr"]


def test_theme_by_column_inverse_la_grille():
    themes = schema.theme_by_column()
    assert themes["taux_presence_pct"] == "Assiduité et travail rendu"
    assert themes["abandon"] == "Cibles"
    assert themes["groupe_td"] == "Leurres annoncés"


def test_aucune_colonne_classee_deux_fois():
    # Un thème est une partition, pas un recouvrement : la somme des effectifs doit
    # égaler le nombre de clés de la table inverse, sinon une colonne a deux thèmes.
    total = sum(len(colonnes) for colonnes in schema.COLUMN_THEMES.values())
    assert total == len(schema.theme_by_column())


def test_unclassified_et_unknown_se_repondent():
    grille = list(schema.theme_by_column())
    assert schema.unclassified(grille) == ()
    assert schema.unknown(grille) == ()

    assert schema.unclassified([*grille, "colonne_inventee"]) == ("colonne_inventee",)
    assert schema.unknown(grille[1:]) == (grille[0],)


@pytest.mark.skipif(
    not (settings.raw_dir / bronze.SOURCES["etudiants"]).exists(),
    reason="données non approvisionnées (cf. data/README.md)",
)
def test_la_grille_couvre_exactement_les_colonnes_du_jeu():
    # Le seul test qui touche aux vraies données : c'est la propriété que le notebook
    # affiche, et la seule que le code garantisse sur la grille de lecture.
    colonnes = pd.read_csv(
        settings.raw_dir / bronze.SOURCES["etudiants"],
        encoding="utf-8-sig",
        nrows=0,
    ).columns

    assert schema.unclassified(colonnes) == ()
    assert schema.unknown(colonnes) == ()
