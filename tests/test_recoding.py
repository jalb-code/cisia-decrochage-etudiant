"""Tests du **mécanisme** de recodage — agnostique du cas d'usage.

Le vocabulaire est passé en paramètre : ces tests n'emploient donc pas le vocabulaire
métier (`preparation.CANONICAL_MODALITIES`, testé dans `test_preparation`) mais une
table de test, pour vérifier le comportement de la brique et non le contrat du projet.
"""

import pandas as pd

from decrochage_l1.data.utils import recoding_utils

# Vocabulaire de test — la brique ne connaît aucune colonne du cas d'usage.
VOCABULAIRE = {
    "sexe": {"femme": ("f", "femme"), "homme": ("h", "homme")},
    "couleur": {"rouge": ("rge", "rouge")},
}


def test_canonical_by_variant_inverse_le_vocabulaire():
    correspondance = recoding_utils.canonical_by_variant("sexe", VOCABULAIRE)
    assert correspondance["f"] == "femme"
    assert correspondance["femme"] == "femme"
    assert correspondance["h"] == "homme"


def test_canonical_by_variant_colonne_hors_vocabulaire():
    assert recoding_utils.canonical_by_variant("filiere", VOCABULAIRE) == {}


def test_recode_ramene_les_synonymes_selon_le_vocabulaire():
    data = pd.DataFrame({"sexe": ["f", "femme", "h"], "note": [12, 15, 9]})
    recoded, colonnes = recoding_utils.recode(data, VOCABULAIRE)
    assert list(recoded["sexe"]) == ["femme", "femme", "homme"]
    assert colonnes == ("sexe",)


def test_recode_ne_touche_pas_les_colonnes_hors_vocabulaire():
    """Une colonne sans synonyme n'est pas recodée, et n'est pas signalée."""
    data = pd.DataFrame({"filiere": ["droit", "gestion"], "note": [12, 15]})
    recoded, colonnes = recoding_utils.recode(data, VOCABULAIRE)
    assert list(recoded["filiere"]) == ["droit", "gestion"]
    assert colonnes == ()


def test_recode_laisse_intacte_une_modalite_hors_table():
    """Le recodage n'invente rien : une valeur inattendue doit rester visible."""
    data = pd.DataFrame({"sexe": ["f", "martien"]})
    recoded, _ = recoding_utils.recode(data, VOCABULAIRE)
    assert sorted(recoded["sexe"]) == ["femme", "martien"]
