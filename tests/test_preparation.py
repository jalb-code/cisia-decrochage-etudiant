"""Tests de la mise en forme du cas d'usage — vocabulaire métier, conformation, transform, gold."""

import pandas as pd
import pytest

from decrochage_l1.data import preparation
from decrochage_l1.data.utils import profiling_utils as profiling
from decrochage_l1.data.utils import recoding_utils

# --- Vocabulaire métier -------------------------------------------------------


def test_le_vocabulaire_cible_est_declare_en_forme_normalisee():
    """Clés et cibles viennent de `normalize_text` : minuscules, sans accent."""
    for groupes in preparation.CANONICAL_MODALITIES.values():
        for canonique, variantes in groupes.items():
            assert canonique == canonique.lower()
            assert all(variante == variante.lower() for variante in variantes)


def test_autre_et_non_renseigne_ne_fusionnent_pas():
    """Une identité déclarée (`nb`/`autre`) n'est pas une absence de réponse (`nr`)."""
    correspondance = recoding_utils.canonical_by_variant("sexe", preparation.CANONICAL_MODALITIES)
    assert correspondance["nr"] == "non renseigné"
    assert correspondance["nb"] != correspondance["nr"]


# --- Conformation -------------------------------------------------------------


def test_conform_type_sans_rien_supprimer():
    data = pd.DataFrame(
        {
            "distance": ["12.0 km", "2,2"],
            "quand": ["2024-09-27", "04 Sep 2024"],
            "filiere": [" GESTION ", "Gestion"],
            "abandon": ["0", "1"],
        }
    )
    conformed = preparation.conform(data, profiling.profile_columns(data))

    assert conformed.shape == data.shape  # aucune ligne ni colonne perdue
    assert list(conformed["distance"]) == [12.0, 2.2]
    assert conformed["quand"].dt.day.tolist() == [27, 4]
    assert list(conformed["filiere"]) == ["gestion", "gestion"]
    assert list(conformed["abandon"]) == [0, 1]


def test_conform_ne_fusionne_pas_les_modalites():
    """« F » et « Femme » disent peut-être la même chose : c'est une décision, pas une forme."""
    data = pd.DataFrame({"sexe": ["F", "Femme", "f", "Homme"]})
    conformed = preparation.conform(data, profiling.profile_columns(data))
    assert set(conformed["sexe"]) == {"f", "femme", "homme"}


def test_conform_laisse_un_booleen_en_toutes_lettres_au_recodage():
    data = pd.DataFrame({"boursier": ["Oui", "N", "non", "O"]})
    conformed = preparation.conform(data, profiling.profile_columns(data))
    assert conformed["boursier"].dtype == "string"


def test_une_cellule_vide_devient_un_manquant_pas_une_modalite():
    """Sinon la chaîne vide se compterait comme une catégorie de plein droit en EDA."""
    data = pd.DataFrame({"mention": ["Bien", "", "   ", "Passable"]})
    conformed = preparation.conform(data, profiling.profile_columns(data))
    assert conformed["mention"].isna().sum() == 2
    assert conformed["mention"].nunique() == 2


def test_un_entier_a_trous_ne_devient_pas_flottant():
    data = pd.DataFrame({"motivation": ["3", "", "5"]})
    conformed = preparation.conform(data, profiling.profile_columns(data))
    assert conformed["motivation"].dtype == "Int64"


def test_conform_est_idempotent_sur_le_typage():
    """Rejouer la mise en forme ne doit rien changer — sinon elle détruirait de l'information."""
    data = pd.DataFrame({"a": ["1,5", "2.5"], "b": ["Nord", " nord "]})
    profile = profiling.profile_columns(data)
    once = preparation.conform(data, profile)
    twice = preparation.conform(once.astype(str), profiling.profile_columns(once.astype(str)))
    pd.testing.assert_frame_equal(once, twice, check_dtype=False)


# --- transform : conformer, recoder, dédoublonner -----------------------------


def test_transform_recode_selon_le_vocabulaire_du_cas_d_usage():
    data = pd.DataFrame(
        {
            "sexe": ["NB", "nr"],  # identité déclarée ≠ non-réponse
            "bac_type": ["GEN", "Technologique"],
            "mention_bac": ["ab", "tb"],
            "boursier": ["O", "0"],
        }
    )
    result, stats = preparation.transform(data, profiling.profile_columns(data))
    assert list(result["sexe"]) == ["autre", "non renseigné"]
    assert list(result["bac_type"]) == ["general", "technologique"]
    assert list(result["mention_bac"]) == ["assez bien", "tres bien"]
    assert list(result["boursier"]) == ["oui", "non"]
    assert set(stats.recoded_columns) == {"sexe", "bac_type", "mention_bac", "boursier"}


def test_transform_dedoublonne_apres_conformation_et_recodage():
    """Deux lignes rendues jumelles par l'écriture puis le vocabulaire ne comptent qu'une fois."""
    data = pd.DataFrame({"sexe": ["F", "Femme", "H"], "age": ["20", "20", "21"]})
    result, stats = preparation.transform(data, profiling.profile_columns(data))
    assert stats.n_duplicates_removed == 1
    assert (stats.n_rows_source, stats.n_rows) == (3, 2)
    assert sorted(result["sexe"]) == ["femme", "homme"]


def test_transform_ne_perd_aucune_colonne_ni_valeur_porteuse_d_information():
    data = pd.DataFrame({"id": ["a", "b"], "note": ["12", ""], "constante": ["x", "x"]})
    result, stats = preparation.transform(data, profiling.profile_columns(data))
    assert (stats.n_columns, stats.n_rows) == (3, 2)
    assert result["note"].isna().sum() == 1  # un manquant reste manquant : aucune imputation
    assert result["constante"].nunique() == 1  # une variance nulle n'est pas un motif de retrait


# --- build_gold : exclusions de principe et features dérivées -----------------


def _silver_reduit() -> pd.DataFrame:
    """Un silver minimal : de quoi vérifier les retraits et dériver les deux features."""
    entier = lambda valeurs: pd.array(valeurs, dtype="Int64")  # noqa: E731
    return pd.DataFrame(
        {
            "student_id": ["a", "b"],
            "nb_devoirs_total": entier([10, 8]),
            "nb_devoirs_rendus": entier([8, 8]),
            "retards_rendus": entier([2, 0]),
            "abandon": entier([1, 0]),
        }
    )


def test_build_gold_retire_les_colonnes_passees_et_conserve_les_cibles():
    """Le drop applique la liste ; une cible n'y figure jamais - le gold la garde pour §9."""
    gold, res = preparation.build_gold(_silver_reduit(), ["student_id"])
    assert "student_id" not in gold.columns
    assert "abandon" in gold.columns
    assert res.dropped == ("student_id",)


def test_build_gold_derive_les_features_sur_le_total_attendu():
    """taux_rendu et ratio_retards se rapportent tous deux à nb_devoirs_total."""
    gold, res = preparation.build_gold(_silver_reduit(), [])
    assert gold["taux_rendu"].tolist() == pytest.approx([0.8, 1.0])  # 8/10, 8/8
    assert gold["ratio_retards"].tolist() == pytest.approx([0.2, 0.0])  # 2/10, 0/8
    assert res.derived == ("taux_rendu", "ratio_retards")


def test_build_gold_protege_la_division_par_zero_ou_absente():
    """Un dénominateur nul ou manquant donne NaN, jamais inf - garde-fou de robustesse."""
    entier = lambda valeurs: pd.array(valeurs, dtype="Int64")  # noqa: E731
    silver = pd.DataFrame(
        {
            "nb_devoirs_total": entier([0, pd.NA]),
            "nb_devoirs_rendus": entier([0, 3]),
            "retards_rendus": entier([0, 1]),
        }
    )
    gold, _ = preparation.build_gold(silver, [])
    assert gold["taux_rendu"].isna().all()
    assert gold["ratio_retards"].isna().all()
