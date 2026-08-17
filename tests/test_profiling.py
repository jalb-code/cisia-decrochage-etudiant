import pandas as pd
import pytest

from decrochage_l1.data.utils import profiling_utils as profiling


def _csv(tmp_path, content: str, name: str = "source.csv", encoding: str = "utf-8") -> object:
    path = tmp_path / name
    path.write_text(content, encoding=encoding)
    return path


# --- Niveau fichier -----------------------------------------------------------


def test_detect_encoding_reconnait_le_bom_utf8(tmp_path):
    path = _csv(tmp_path, "a,b\n1,2\n", encoding="utf-8-sig")
    assert profiling.detect_encoding(path) == ("utf-8-sig", True)


def test_detect_encoding_distingue_utf8_et_cp1252(tmp_path):
    utf8 = _csv(tmp_path, "ville\nDéols\n", name="u.csv", encoding="utf-8")
    cp1252 = _csv(tmp_path, "ville\nDéols\n", name="c.csv", encoding="cp1252")
    assert profiling.detect_encoding(utf8) == ("utf-8", False)
    assert profiling.detect_encoding(cp1252) == ("cp1252", False)


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_detect_delimiter_couvre_les_separateurs_usuels(tmp_path, delimiter):
    lines = [delimiter.join(["nom", "age", "ville"]), delimiter.join(["ana", "30", "lyon"])]
    path = _csv(tmp_path, "\n".join(lines) + "\n")
    assert profiling.detect_delimiter(path, "utf-8") == delimiter


def test_read_as_text_compte_les_lignes_en_double(tmp_path):
    path = _csv(tmp_path, "a,b\n1,2\n1,2\n3,4\n")
    _, profile = profiling.read_as_text(path)
    assert (profile.n_rows, profile.n_columns, profile.n_duplicate_rows) == (3, 2, 1)


def test_read_as_text_ninterprete_aucun_marqueur_dabsence(tmp_path):
    """Le littéral « NA » doit rester lisible : le module constate, il ne convertit pas."""
    path = _csv(tmp_path, "note,ville\n12,lyon\nNA,\n")
    data, _ = profiling.read_as_text(path)
    assert list(data["note"]) == ["12", "NA"]
    assert list(data["ville"]) == ["lyon", ""]


# --- Motifs -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-09-27", r"\d{4}\-\d{2}\-\d{2}"),
        ("04 Sep 2024", r"\d{2}\ \w{3}\ \d{4}"),
        ("ETU-03041", r"\w{3}\-\d{5}"),
        ("77,5%", r"\d{2},\d%"),
    ],
)
def test_generalize_pattern(value, expected):
    assert profiling.generalize_pattern(value) == expected


def test_generalize_pattern_tronque_les_motifs_longs():
    """Un texte libre produit un motif interminable : il est coupé, pas déversé dans le tableau."""
    pattern = profiling.generalize_pattern("a1" * 40, max_length=10)
    assert pattern.endswith("…") and len(pattern) == 11


def test_le_motif_se_lit_sur_un_nombre_reste_en_texte():
    """Le seul cas utile : pandas n'a pas su typer, donc l'écriture est en cause."""
    values = pd.Series(["12.0 km", "2,2", "18.8"])
    profile = profiling.profile_column(values.rename("distance"), "object")
    assert profile["n_motifs"] == 3
    assert profile["motif_dominant"] != ""


@pytest.mark.parametrize("dtype", ["int64", "float64", "datetime64[ns]"])
def test_pas_de_motif_sur_une_colonne_deja_typee_par_pandas(dtype):
    """Pandas a su la lire : compter ses formes ne dirait que son ordre de grandeur."""
    profile = profiling.profile_column(pd.Series(["9", "12", "103"]).rename("age"), dtype)
    assert (profile["motif_dominant"], profile["couverture_motif_%"], profile["n_motifs"]) == (
        "",
        "",
        "",
    )


@pytest.mark.parametrize(
    "values",
    [
        ["Sciences & Technologies", "Droit", "Lettres & Langues"],  # texte
        ["nord", "sud", "nord", "sud"] * 20,  # catégoriel
        ["Oui", "N", "non", "0", "1"],  # booléen
    ],
)
def test_pas_de_motif_sur_un_libelle(values):
    """Une longueur de libellé n'est pas une convention d'écriture : casse et espaces
    se lisent sur `n_distinct` face à `n_distinct_normalise`, que le motif ignore."""
    profile = profiling.profile_column(pd.Series(values).rename("c"), "object")
    assert profile["n_motifs"] == ""


# --- Types sémantiques --------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["L1"] * 5, "constant"),
        (["Oui", "N", "non", "0", "1"], "booleen"),
        (["12", "7", "103"], "entier"),
        (["12.0 km", "2,2", "18.8"], "decimal"),
        (["2024-09-27", "04 Sep 2024", "26/09/2024"] * 5, "date"),
        (["nord", "sud", "nord", "sud"] * 20, "categoriel"),
    ],
)
def test_infer_semantic_type(values, expected):
    assert profiling.infer_semantic_type(pd.Series(values, name="c")) == expected


def test_un_flottant_rond_reste_decimal():
    """« 0.0 » est un décimal mal cadré, pas un entier : le type qualifie l'écriture."""
    assert profiling.infer_semantic_type(pd.Series(["0.0", "9.0", "15.0"])) == "decimal"


def test_une_cle_reste_identifiable_malgre_les_doublons():
    """Le seuil de quasi-unicité doit reconnaître la clé *et* laisser voir les doublons."""
    values = [f"ETU-{i:05d}" for i in range(100)] + ["ETU-00000", "ETU-00001"]
    assert profiling.infer_semantic_type(pd.Series(values)) == "identifiant"


def test_pas_didentifiant_sur_un_fichier_minuscule():
    """Sur 8 lignes, toute colonne variée paraît unique : ne rien affirmer."""
    assert profiling.infer_semantic_type(pd.Series(["710", "830", "930", "980"])) == "entier"


# --- Non-conformité -----------------------------------------------------------


def test_non_conformite_numerique_compte_virgules_et_unites():
    values = pd.Series(["1.0", "2.0", "3,0", "4.0 km"])
    profile = profiling.profile_column(values.rename("distance"))
    assert profile["type_semantique"] == "decimal"
    assert profile["non_conforme_%"] == 50.0


def test_non_conformite_texte_compte_les_ecritures_minoritaires():
    values = pd.Series(["Gestion"] * 8 + [" GESTION ", "gestion"])
    profile = profiling.profile_column(values.rename("filiere"))
    assert profile["n_distinct"] == 3
    assert profile["n_distinct_normalise"] == 1
    assert profile["non_conforme_%"] == 20.0


def test_les_dates_multi_formats_sont_signalees():
    values = pd.Series(["2024-09-27"] * 6 + ["26/09/2024"] * 2 + ["04 Sep 2024"] * 2)
    profile = profiling.profile_column(values.rename("date_inscription"))
    assert profile["type_semantique"] == "date"
    assert profile["non_conforme_%"] == 40.0
    assert "3 formats" in profile["remarques"]


def test_detect_date_formats_rend_le_jeu_minimal_par_frequence():
    values = pd.Series(["2024-09-27"] * 5 + ["26/09/2024"] * 3 + ["04 Sep 2024"])
    assert profiling.detect_date_formats(values) == ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y")


# --- Bornes -------------------------------------------------------------------


def test_les_bornes_numeriques_se_lisent_sur_la_grandeur():
    """Comparé comme du texte, « 9,5 » dépasserait « 12.0 km » : les bornes se lisent parsées."""
    values = pd.Series(["12.0 km", "9,5", "120.55", "0,1"])
    profile = profiling.profile_column(values.rename("distance"))
    assert (profile["min"], profile["max"]) == ("0.1", "120.55")


def test_les_bornes_entieres_nont_pas_de_partie_decimale():
    profile = profiling.profile_column(pd.Series(["12", "7", "103"]).rename("age"))
    assert (profile["min"], profile["max"]) == ("7", "103")


def test_les_bornes_de_date_ignorent_le_format_decriture():
    values = pd.Series(["2024-09-27", "04 Sep 2024", "26/09/2024"] * 5)
    profile = profiling.profile_column(values.rename("date_inscription"))
    assert (profile["min"], profile["max"]) == ("2024-09-04", "2024-09-27")


@pytest.mark.parametrize(
    "values",
    [
        ["nord", "sud", "nord", "sud"] * 20,  # catégoriel
        ["Oui", "N", "non", "0", "1"],  # booléen
        ["L1"] * 5,  # constant
    ],
)
def test_pas_de_bornes_sur_une_colonne_non_ordonnable(values):
    """L'ordre lexicographique de modalités n'a aucun sens métier : ne rien afficher."""
    profile = profiling.profile_column(pd.Series(values).rename("c"))
    assert (profile["min"], profile["max"]) == ("", "")


def test_le_taux_de_null_ignore_les_blancs():
    profile = profiling.profile_column(pd.Series(["a", "", "   ", "b"]).rename("c"))
    assert profile["null_%"] == 50.0


# --- Inventaire des motifs d'écriture -----------------------------------------


def test_pattern_breakdown_compte_les_motifs_et_donne_un_exemple():
    """C'est l'exemple qui rend le motif lisible ; l'effectif, ce que le dominant cache."""
    values = pd.Series(["18.8", "5.5", "42,8", "12.0 km", "9.7 km"])
    breakdown = profiling.pattern_breakdown(values)

    assert set(breakdown.columns) == {"motif", "n", "part_%", "exemple"}
    assert len(breakdown) == 5  # cinq écritures, cinq motifs
    assert breakdown["n"].sum() == 5
    assert all(exemple in values.tolist() for exemple in breakdown["exemple"])


def test_pattern_breakdown_ordonne_par_frequence_et_ramene_a_100():
    values = pd.Series(["2024-09-02"] * 3 + ["02/09/2024"] * 2)
    breakdown = profiling.pattern_breakdown(values)

    assert list(breakdown["n"]) == [3, 2]
    assert round(breakdown["part_%"].sum()) == 100


def test_pattern_breakdown_se_tait_au_dela_du_plafond():
    """Un texte libre produit un motif par longueur : la liste cesse d'être lisible."""
    assert profiling.pattern_breakdown(pd.Series([f"{'a' * n}" for n in range(1, 30)])) is None


def test_pattern_breakdown_ignore_les_manquants():
    assert profiling.pattern_breakdown(pd.Series(["", "   ", None])) is None
