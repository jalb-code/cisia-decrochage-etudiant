import pandas as pd

from decrochage_l1.data.utils import profiling_utils as profiling

_OVERVIEW = [
    "colonne",
    "type_reel",
    "type_semantique",
    "n_distinct",
    "n_distinct_normalise",
    "min",
    "max",
    "null_%",
]


def _source(tmp_path):
    """CSV de 25 lignes couvrant les quatre cas du rapport, espaces dans le nom compris."""
    frame = pd.DataFrame(
        {
            "cle": [f"ETU-{i:05d}" for i in range(25)],  # 25 modalités : au-delà du plafond
            "filiere": [" GESTION ", "Gestion", "gestion"] * 8
            + ["Droit"],  # 2 modalités, 4 écritures
            "note": [f"{10 + i % 5},5" for i in range(25)],  # 5 modalités
            "libelle": ["<script>alert(1)</script>"] * 25,  # constante, à échapper
        }
    )
    path = tmp_path / "dataset test V5.csv"
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def _page(tmp_path, **kwargs):
    profile = profiling.profile_csv(_source(tmp_path), report_dir=tmp_path / "reports", **kwargs)
    return profile.report_path.read_text(encoding="utf-8")


# --- Inventaire des modalités -------------------------------------------------


def test_modality_breakdown_liste_les_ecritures_par_frequence():
    values = pd.Series([" GESTION ", "Gestion", "gestion"] * 3 + ["Droit"])
    breakdown = profiling.modality_breakdown(values)

    assert list(breakdown["modalite"]) == ["gestion", "droit"]
    assert list(breakdown["n"]) == [9, 1]
    assert breakdown.loc[0, "part_%"] == 90.0
    assert list(breakdown.loc[0, "ecritures"]) == [" GESTION ", "Gestion", "gestion"]


def test_modality_breakdown_sabstient_au_dela_du_plafond():
    """Le plafond garde la lisibilité : au-delà, le profil chiffré suffit."""
    values = pd.Series([str(i) for i in range(25)])
    assert profiling.modality_breakdown(values) is None
    assert profiling.modality_breakdown(values, max_modalities=25) is not None


def test_modality_breakdown_ne_rend_rien_sur_une_colonne_vide():
    assert profiling.modality_breakdown(pd.Series(["", "   "])) is None


# --- Vue resserrée ------------------------------------------------------------


def test_overview_resserre_sans_amputer_le_profil(tmp_path):
    """Une seule mesure, deux restitutions : la vue d'écran ne retire rien de `columns`."""
    profile = profiling.profile_csv(_source(tmp_path))

    assert list(profile.overview().columns) == _OVERVIEW
    assert len(profile.columns.columns) == 14
    assert "non_conforme_%" in profile.columns.columns


# --- Rapport HTML -------------------------------------------------------------


def test_profile_csv_necrit_rien_par_defaut(tmp_path):
    """Mesurer ne touche pas au disque tant qu'on ne l'a pas demandé."""
    profile = profiling.profile_csv(_source(tmp_path))

    assert profile.report_path is None
    assert not list(tmp_path.rglob("*.html"))


def test_profile_csv_ecrit_le_rapport_demande(tmp_path):
    profile = profiling.profile_csv(_source(tmp_path), report_dir=tmp_path / "reports")

    assert profile.report_path == tmp_path / "reports" / "profil-dataset_test_V5.html"
    assert profile.report_path.exists()


def test_le_rapport_porte_les_quatorze_indicateurs(tmp_path):
    page = _page(tmp_path)
    for indicateur in ["motif_dominant", "n_motifs", "non_conforme_%", "exemples", "remarques"]:
        assert indicateur in page


def test_les_exemples_souvrent_sous_le_plafond_seulement(tmp_path):
    """Trois colonnes énumérables sur quatre : la clé à 25 modalités reste muette."""
    page = _page(tmp_path)

    # `m…` désigne les modales de modalités, `p…` celles des motifs (cf. _columns_section).
    assert page.count('data-modal="m') == 3
    assert page.count('<template id="m') == 3  # un inventaire en réserve par colonne cliquable
    assert "2 modalités" in page  # filiere
    assert "5 modalités" in page  # note


def test_le_plafond_est_parametrable_a_lappel(tmp_path):
    page = _page(tmp_path, max_modalities=1)
    assert page.count('data-modal="m') == 1  # seule la constante tient sous le plafond


def test_les_espaces_de_bord_restent_visibles_dans_les_ecritures(tmp_path):
    """Sans guillemets collés et `white-space: pre`, le navigateur effacerait le défaut à voir."""
    assert "« GESTION »" in _page(tmp_path)


def test_le_rapport_echappe_les_valeurs_de_la_source(tmp_path):
    """Une valeur du CSV ne doit jamais devenir du balisage exécutable.

    Le rapport embarque son propre `<script>` : ce qui est interdit, c'est que la
    *valeur* de la source en produise un.
    """
    page = _page(tmp_path)

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert page.count("<script>") == 1  # celui du rapport, et lui seul
