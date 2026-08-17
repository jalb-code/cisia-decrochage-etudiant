import matplotlib
import numpy as np
import pandas as pd

from decrochage_l1 import eda

matplotlib.use("Agg")  # aucun affichage : les tests de tracé ne vérifient que la structure


# --- Cibles et variables ------------------------------------------------------


def test_class_balance_compte_les_manquants_comme_une_modalite():
    """Sur une cible, une valeur absente est une ligne inapprenable : elle doit se voir."""
    balance = eda.class_balance(pd.Series([1, 0, 0, None], dtype="Int64"))

    assert list(balance["modalite"]) == ["0", "1", eda.MISSING_LABEL]
    assert list(balance["n"]) == [2, 1, 1]
    assert balance["part_%"].sum() == 100.0


def test_imbalance_ratio_vaut_un_a_lequilibre():
    assert eda.imbalance_ratio(pd.Series([0, 1, 0, 1])) == 1.0
    assert eda.imbalance_ratio(pd.Series([0] * 9 + [1])) == 9.0


def test_numeric_overview_rend_une_ligne_par_colonne_avec_lasymetrie():
    data = pd.DataFrame({"a": pd.array([1, 2, 3, None], dtype="Int64"), "b": [0.0, 0.0, 0.0, 12.0]})
    overview = eda.numeric_overview(data).set_index("colonne")

    assert list(overview.index) == ["a", "b"]
    assert overview.loc["a", "n_renseigne"] == 3
    assert "manquants_%" not in overview.columns  # le sujet appartient à missing_overview
    assert overview.loc["a", "mediane"] == 2.0
    assert overview.loc["b", "asymetrie"] > 1  # queue à droite : la moyenne n'est plus le centre


def test_modality_overview_donne_la_dominante_et_la_plus_rare():
    data = pd.DataFrame({"sexe": ["femme"] * 7 + ["homme"] * 2 + ["autre"]})
    overview = eda.modality_overview(data).iloc[0]

    assert (overview["dominante"], overview["part_dominante_%"]) == ("femme", 70.0)
    assert (overview["plus_rare"], overview["part_rare_%"]) == ("autre", 10.0)


def test_rare_modalities_ne_retient_que_le_dessous_du_seuil():
    data = pd.DataFrame({"sexe": ["femme"] * 99 + ["autre"]})
    rares = eda.rare_modalities(data, max_share=0.02)

    assert list(rares["modalite"]) == ["autre"]
    assert (rares.loc[0, "n"], rares.loc[0, "part_%"]) == (1, 1.0)


def test_rare_modalities_rend_un_tableau_vide_mais_typé():
    """Le cas vide doit rester affichable : un tableau sans colonnes casserait la sortie."""
    rares = eda.rare_modalities(pd.DataFrame({"a": ["x", "y"]}), max_share=0.01)
    assert rares.empty and list(rares.columns) == ["colonne", "modalite", "n", "part_%"]


def test_quasi_constant_signale_ce_quaucune_egalite_stricte_ne_verrait():
    data = pd.DataFrame({"presque": ["l1"] * 99 + ["l2"], "variee": list("abcdefghij") * 10})
    quasi = eda.quasi_constant(data, min_share=0.95)

    assert list(quasi["colonne"]) == ["presque"]
    assert quasi.loc[0, "part_%"] == 99.0


# --- Valeurs manquantes -------------------------------------------------------


def test_missing_overview_ne_liste_que_les_colonnes_trouees():
    data = pd.DataFrame({"pleine": [1, 2, 3, 4], "trouee": [1, None, None, 4]})
    overview = eda.missing_overview(data, themes={"trouee": "Ressenti déclaré"})

    assert list(overview["colonne"]) == ["trouee"]
    assert overview.loc[0, "part_%"] == 50.0
    assert overview.loc[0, "theme"] == "Ressenti déclaré"


def test_missing_per_row_oppose_lobserve_a_lattendu_sous_independance():
    """Deux colonnes manquantes sur les MÊMES lignes : la concentration doit sauter aux yeux."""
    data = pd.DataFrame(
        {
            "a": [None] * 50 + list(range(50)),
            "b": [None] * 50 + list(range(50)),
        }
    )
    per_row = eda.missing_per_row(data).set_index("nb_colonnes_manquantes")

    assert per_row.loc[1, "n_lignes_observe"] == 0  # jamais une seule des deux
    assert per_row.loc[1, "n_lignes_attendu"] == 50  # l'indépendance en prévoyait la moitié
    assert per_row.loc[2, "n_lignes_observe"] == 50


def test_missing_per_row_attendu_totalise_les_lignes():
    generator = np.random.default_rng(0)
    data = pd.DataFrame(generator.normal(size=(200, 4))).mask(
        generator.random((200, 4)) < 0.2  # manquants indépendants d'une colonne à l'autre
    )
    per_row = eda.missing_per_row(data)

    assert per_row["n_lignes_attendu"].sum() == 200
    assert per_row["n_lignes_observe"].sum() == 200


def test_missing_vs_target_mesure_lecart_de_taux():
    data = pd.DataFrame({"trouee": [None, None, 1, 1]})
    cible = pd.Series([1, 1, 0, 0])
    ecarts = eda.missing_vs_target(data, cible, n_permutations=50)

    assert ecarts.loc[0, "taux_si_manquant_%"] == 100.0
    assert ecarts.loc[0, "taux_si_present_%"] == 0.0
    assert ecarts.loc[0, "ecart_pt"] == 100.0
    # Le plafond de bruit est dans la même unité que l'écart : des points de %.
    assert ecarts.loc[0, "bruit_95_pt"] == 100.0


def test_missing_vs_target_situe_un_ecart_faible_dans_le_bruit():
    """Trois points d'écart sur un dixième des lignes ne prouvent rien : la p-valeur le dit."""
    generator = np.random.default_rng(0)
    valeurs = generator.normal(size=1000)
    data = pd.DataFrame({"trouee": np.where(generator.random(1000) < 0.1, np.nan, valeurs)})
    ecarts = eda.missing_vs_target(data, pd.Series(generator.integers(0, 2, 1000)))

    assert ecarts.loc[0, "p_permutation"] > 0.05


def test_missing_vs_target_ignore_une_colonne_pleine_ou_entierement_vide():
    data = pd.DataFrame({"pleine": [1, 2], "vide": [None, None]})
    assert eda.missing_vs_target(data, pd.Series([0, 1])).empty


def test_missing_mechanism_rejette_mcar_quand_labsence_depend_dune_observee():
    """L'absence de `trouee` frappe surtout le groupe 'a' : elle dépend d'une observée."""
    generator = np.random.default_rng(0)
    n = 600
    groupe = np.where(generator.random(n) < 0.5, "a", "b")
    manque = np.where(groupe == "a", generator.random(n) < 0.6, generator.random(n) < 0.05)
    data = pd.DataFrame(
        {
            "trouee": np.where(manque, np.nan, generator.normal(size=n)),
            "groupe": groupe,
            "bruit_num": generator.normal(size=n),  # numérique sans rapport avec l'absence
        }
    )
    meca = eda.missing_mechanism(data, ["trouee"], n_permutations=200).set_index("colonne")

    assert meca.loc["trouee", "variable_liee"] == "groupe"
    assert meca.loc["trouee", "type"] == "catégorielle"
    assert bool(meca.loc["trouee", "mcar_rejete"]) is True


def test_missing_mechanism_ne_rejette_pas_mcar_quand_labsence_est_aleatoire():
    """Absence indépendante de tout : aucune observée ne sort de son bruit ⇒ MCAR tenable."""
    generator = np.random.default_rng(1)
    n = 600
    data = pd.DataFrame(
        {
            "trouee": np.where(generator.random(n) < 0.2, np.nan, generator.normal(size=n)),
            "groupe": generator.choice(list("abc"), n),
            "bruit_num": generator.normal(size=n),
        }
    )
    meca = eda.missing_mechanism(data, ["trouee"], n_permutations=200)

    assert bool(meca.loc[0, "mcar_rejete"]) is False
    assert meca.loc[0, "p_permutation"] > 0.05


def test_missing_mechanism_detecte_seul_les_colonnes_trouees_par_defaut():
    data = pd.DataFrame(
        {"pleine": [1, 2, 3, 4], "trouee": [1, None, None, 4], "autre": list("wxyz")}
    )
    meca = eda.missing_mechanism(data, n_permutations=50)
    assert list(meca["colonne"]) == ["trouee"]


# --- Valeurs extrêmes ---------------------------------------------------------


def test_iqr_bounds_applique_la_regle_de_tukey():
    bas, haut = eda.iqr_bounds(pd.Series([1, 2, 3, 4, 5]))
    assert (bas, haut) == (-1.0, 7.0)  # q1=2, q3=4 -> 2 - 1.5*2 et 4 + 1.5*2


def test_domain_check_situe_les_valeurs_dans_leur_domaine():
    data = pd.DataFrame({"note": [5.0, 15.0], "accord": [1, 5]})
    check = eda.domain_check(data, {"note": (0.0, 20.0), "accord": (1.0, 5.0)}).set_index("colonne")

    assert check.loc["note", ["debut_%", "fin_%"]].tolist() == [25.0, 75.0]
    assert check.loc["accord", ["debut_%", "fin_%"]].tolist() == [0.0, 100.0]  # échelle épuisée
    assert check.loc["note", "domaine"] == "[0 ; 20]"
    assert check["n_hors_domaine"].sum() == 0


def test_domain_check_laisse_une_valeur_impossible_sortir_du_cadre():
    """Ramener la position dans [0 ; 100] cacherait exactement ce qu'on cherche."""
    check = eda.domain_check(pd.DataFrame({"note": [0.0, 25.0]}), {"note": (0.0, 20.0)})

    assert check.loc[0, "fin_%"] == 125.0
    assert check.loc[0, "n_hors_domaine"] == 1


def test_domain_check_ignore_une_colonne_sans_plafond_metier():
    """Sans borne haute, une position relative n'a pas de sens."""
    data = pd.DataFrame({"clics": [1, 2], "note": [5.0, 15.0]})
    check = eda.domain_check(data, {"clics": (0.0, float("inf")), "note": (0.0, 20.0)})

    assert list(check["colonne"]) == ["note"]


def test_iqr_outliers_compte_les_valeurs_rares():
    outliers = eda.iqr_outliers(pd.DataFrame({"clics": [10.0] * 20 + [900.0]})).set_index("colonne")

    assert outliers.loc["clics", "n_hors_iqr"] == 1
    assert outliers.loc["clics", "part_%"] == 4.76


def test_iqr_mask_repond_sur_les_lignes_et_non_sur_les_valeurs():
    """Deux colonnes peuvent signaler la même ligne : ce sont les lignes touchées qui décident."""
    data = pd.DataFrame({"a": [1.0, 1.0, 1.0, 1.0, 50.0], "b": [2.0, 2.0, 2.0, 2.0, 90.0]})
    masque = eda.iqr_mask(data)

    assert masque.to_numpy().sum() == 2  # deux valeurs
    assert int(masque.any(axis=1).sum()) == 1  # une seule ligne


# --- Associations -------------------------------------------------------------


def test_correlation_pairs_ne_rend_chaque_paire_quune_fois():
    data = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8], "c": [4, 3, 2, 1]})
    pairs = eda.correlation_pairs(data)

    assert len(pairs) == 3  # 3 colonnes -> 3 paires, pas 6 ni 9
    assert set(pairs.columns) == {"variable_1", "variable_2", "correlation"}


def test_correlation_pairs_trie_sur_la_valeur_absolue():
    """Une redondance négative est une redondance : le signe ne doit pas la reléguer."""
    data = pd.DataFrame({"a": [1, 2, 3, 4], "oppose": [4, 3, 2, 1], "tiede": [1, 3, 2, 4]})
    pairs = eda.correlation_pairs(data, threshold=0.9)

    assert list(pairs.loc[0, ["variable_1", "variable_2"]]) == ["a", "oppose"]
    assert pairs.loc[0, "correlation"] == -1.0


def test_cramers_v_vaut_un_sur_une_dependance_parfaite():
    left = pd.Series(["a", "a", "b", "b"])
    right = pd.Series([0, 0, 1, 1])
    assert eda.cramers_v(left, right) == 1.0


def test_cramers_v_est_symetrique():
    left = pd.Series(list("aabbcc"))
    right = pd.Series([0, 1, 0, 1, 1, 1])
    assert eda.cramers_v(left, right) == eda.cramers_v(right, left)


def test_cramers_v_compte_un_manquant_comme_une_modalite():
    """Manquer peut être le signal : l'écarter du tableau de contingence l'effacerait."""
    left = pd.Series(["a", "a", None, None], dtype="string")
    right = pd.Series([0, 0, 1, 1])
    assert eda.cramers_v(left, right) == 1.0


def test_cramers_v_rend_zero_sur_une_colonne_constante():
    constante = pd.Series(["l1"] * 4)
    assert eda.cramers_v(constante, pd.Series([0, 1, 0, 1])) == 0.0


def test_cramers_v_reste_sous_son_bruit_quand_les_variables_sont_independantes():
    """Le seul énoncé défendable sur une association faible : elle ne sort pas du bruit."""
    generator = np.random.default_rng(0)
    data = pd.DataFrame(
        {
            "leurre": generator.choice(list("abcde"), size=1500),
            "cible": generator.integers(0, 2, size=1500),
        }
    )
    observe = eda.cramers_v(data["leurre"], data["cible"])
    bruit = eda.cramers_v_noise(data["leurre"], data["cible"], n_permutations=100)

    assert 0 < observe < bruit


def test_cramers_v_noise_est_reproductible_a_graine_fixee():
    data = pd.DataFrame({"x": list("abab") * 50, "y": [0, 1] * 100})
    premier = eda.cramers_v_noise(data["x"], data["y"], n_permutations=50, random_state=7)
    second = eda.cramers_v_noise(data["x"], data["y"], n_permutations=50, random_state=7)
    assert premier == second


def test_cramers_v_matrix_est_symetrique_et_sa_diagonale_vaut_un():
    data = pd.DataFrame({"a": list("aabb"), "b": list("abab"), "c": list("aabb")})
    matrix = eda.cramers_v_matrix(data)

    assert list(np.diag(matrix)) == [1.0, 1.0, 1.0]
    assert matrix.loc["a", "c"] == matrix.loc["c", "a"] == 1.0


def test_categorical_association_situe_chaque_variable_par_rapport_au_bruit():
    # Indépendance EXACTE par construction : cinq modalités et deux classes de
    # périodes premières entre elles répartissent la cible à parts égales partout.
    cible = pd.Series([0, 1] * 250)
    data = pd.DataFrame({"reelle": cible.map({0: "bas", 1: "haut"}), "leurre": list("abcde") * 100})
    association = eda.categorical_association(
        data, ["reelle", "leurre"], cible, n_permutations=99
    ).set_index("colonne")

    assert association.loc["reelle", "v_cramer"] == 1.0
    assert association.loc["reelle", "p_permutation"] == 0.01  # le plancher : 1 / (99 + 1)
    assert association.loc["leurre", "v_cramer"] == 0.0
    assert association.loc["leurre", "p_permutation"] == 1.0  # tout tirage atteint zéro


def test_la_p_valeur_de_permutation_ne_vaut_jamais_zero():
    """Un plancher à 1/(n+1) : cent tirages ne peuvent pas prouver l'impossible."""
    ceiling, p_value = eda._permutation_summary(10.0, np.zeros(99))
    assert (ceiling, p_value) == (0.0, 0.01)


def test_categorical_association_compte_le_manquant_comme_un_groupe():
    data = pd.DataFrame({"mention": pd.array(["bien", "bien", None, None], dtype="string")})
    association = eda.categorical_association(
        data, ["mention"], pd.Series([0, 1, 0, 1]), n_permutations=20
    )
    assert association.loc[0, "n_groupes"] == 2  # une modalité renseignée + le manquant


def test_matrix_pairs_sert_aussi_une_matrice_non_signee():
    """Le même dépliage doit servir les corrélations et les V de Cramér."""
    matrix = pd.DataFrame(
        [[1.0, 0.9, 0.1], [0.9, 1.0, 0.2], [0.1, 0.2, 1.0]], index=list("abc"), columns=list("abc")
    )
    pairs = eda.matrix_pairs(matrix, threshold=0.5, name="v_cramer")

    assert list(pairs.columns) == ["variable_1", "variable_2", "v_cramer"]
    assert len(pairs) == 1
    assert list(pairs.loc[0]) == ["a", "b", 0.9]


def test_modality_counts_ordonne_et_garde_les_manquants():
    counts = eda.modality_counts(pd.Series(["a", "a", "b", None], dtype="string"))
    assert list(counts.index) == ["b", eda.MISSING_LABEL, "a"]  # croissant
    assert counts.loc[eda.MISSING_LABEL] == 1


def test_group_spread_mesure_lecart_dans_lunite_de_la_cible():
    groupes = pd.Series(list("aabb"))
    notes = pd.Series([10.0, 12.0, 16.0, 18.0])
    assert eda.group_spread(notes, groupes) == 6.0  # 17 - 11


def test_group_spread_ignore_les_manquants_de_la_cible():
    groupes = pd.Series(list("aabb"))
    notes = pd.Series([10.0, None, 16.0, 18.0])
    assert eda.group_spread(notes, groupes) == 7.0  # 17 - 10


def test_group_spread_table_confronte_chaque_cible_a_son_bruit():
    # Une variable qui découpe exactement la note, une autre sans aucun rapport.
    data = pd.DataFrame({"reelle": list("aabb") * 50, "plat": list("abab") * 50})
    notes = pd.Series([10.0, 10.0, 18.0, 18.0] * 50)
    table = eda.group_spread_table(
        data, ["reelle", "plat"], {"note": notes}, n_permutations=99
    ).set_index("colonne")

    assert table.loc["reelle", "ecart_observe"] == 8.0
    assert table.loc["reelle", "p_permutation"] == 0.01
    assert table.loc["plat", "ecart_observe"] == 0.0
    assert table.loc["plat", "p_permutation"] == 1.0


def test_target_rate_by_modality_garde_les_manquants_et_leffectif():
    data = pd.DataFrame({"mention": ["bien", "bien", None]})
    taux = eda.target_rate_by_modality(data, "mention", pd.Series([0, 1, 1])).set_index("modalite")

    assert taux.loc["bien", "n"] == 2
    assert taux.loc["bien", "taux_%"] == 50.0
    assert taux.loc[eda.MISSING_LABEL, "taux_%"] == 100.0


# --- Tracé --------------------------------------------------------------------


def test_panels_masque_les_cases_excedentaires():
    figure, axes = eda.panels(5, n_cols=4)
    assert len(axes) == 5
    assert sum(not axis.get_visible() for axis in figure.axes) == 3  # 2 rangées de 4 pour 5


def test_panels_resserre_la_grille_sous_le_nombre_de_colonnes():
    """Un seul panneau ne doit pas rendre une figure de quatre colonnes vides."""
    figure, axes = eda.panels(1, n_cols=4)
    assert len(axes) == len(figure.axes) == 1


def test_plot_histograms_rend_un_panneau_par_colonne():
    data = pd.DataFrame({"a": range(30), "b": range(30)})
    figure = eda.plot_histograms(data, n_cols=2)
    assert len(figure.axes) == 2


def test_plot_histograms_plafonne_les_classes_aux_valeurs_distinctes():
    """Trente classes pour trois valeurs rendraient un peigne de barres vides."""
    figure = eda.plot_histograms(pd.DataFrame({"nb_ue": [5, 6, 7] * 10}), bins=30)
    assert len(figure.axes[0].patches) == 3


def test_plot_boxplots_rend_un_panneau_par_colonne():
    data = pd.DataFrame({"n": [1.0, 2.0, 3.0, 40.0], "autre": [1.0, 1.0, 2.0, 2.0]})
    assert len(eda.plot_boxplots(data).axes) == 2


def test_plot_boxplots_inscrit_son_annotation_dans_le_panneau():
    """L'annotation porte le compte : c'est elle qui dispense du tableau en regard."""
    figure = eda.plot_boxplots(
        pd.DataFrame({"n": [1.0, 2.0, 3.0]}), annotations={"n": "3 hors IQR"}
    )
    assert [text.get_text() for text in figure.axes[0].texts] == ["3 hors IQR"]


def test_plot_bars_inscrit_la_valeur_au_bout_de_chaque_barre():
    figure = eda.plot_bars({"taux": pd.Series([25.0, 31.5], index=["a", "b"])}, labels="{:.1f}")
    assert [text.get_text() for text in figure.axes[0].texts] == ["25.0", "31.5"]


def test_plot_bars_reserve_la_place_des_etiquettes_sur_laxe():
    """Sans marge élargie, l'étiquette du maximum sortirait du cadre."""
    serie = {"taux": pd.Series([10.0, 100.0], index=["a", "b"])}
    assert (
        eda.plot_bars(serie, labels="{:.0f}").axes[0].get_xlim()[1]
        > (eda.plot_bars(serie).axes[0].get_xlim()[1])
    )


def test_plot_grouped_bars_porte_une_legende_par_serie():
    frame = pd.DataFrame({"observé": [10, 20], "attendu": [12, 18]}, index=[0, 1])
    figure = eda.plot_grouped_bars(frame, labels="{:.0f}")

    assert [text.get_text() for text in figure.axes[0].get_legend().get_texts()] == [
        "observé",
        "attendu",
    ]
    assert len(figure.axes[0].texts) == 4  # une étiquette par barre


def test_plot_intervals_trace_une_bande_et_un_point_par_ligne():
    frame = pd.DataFrame({"ecart": [2.8, -1.0], "bruit": [3.7, 4.4]}, index=["a", "b"])
    figure = eda.plot_intervals(frame, "ecart", "bruit")
    axis = figure.axes[0]

    assert len(axis.patches) == 2  # une bande par ligne
    assert len(axis.collections) == 1  # les points, en un seul nuage
    assert len(axis.get_legend().get_texts()) == 2


def test_plot_domain_occupancy_etiquette_les_bornes_observees():
    check = eda.domain_check(pd.DataFrame({"note": [5.0, 15.0]}), {"note": (0.0, 20.0)})
    figure = eda.plot_domain_occupancy(check)

    assert [text.get_text() for text in figure.axes[0].texts] == ["5", "15"]
    # Le domaine déclaré reste lisible dans l'étiquette d'axe, l'échelle étant relative.
    assert figure.axes[0].get_yticklabels()[0].get_text() == "note  [0 ; 20]"


def test_plot_bars_trace_la_reference_et_partage_lechelle():
    petit = pd.Series([20.0, 40.0], index=["a", "b"])
    grand = pd.Series([5.0, 95.0], index=["x", "y"])
    figure = eda.plot_bars({"petit": petit, "grand": grand}, reference=28.4, n_cols=2)

    assert len(figure.axes[0].lines) == 1  # le trait du niveau d'ensemble
    assert figure.axes[0].get_xlim() == figure.axes[1].get_xlim()


def test_plot_bars_admet_des_echelles_independantes():
    figure = eda.plot_bars(
        {"a": pd.Series([1.0], index=["x"]), "b": pd.Series([100.0], index=["y"])},
        n_cols=2,
        shared_scale=False,
    )
    assert figure.axes[0].get_xlim() != figure.axes[1].get_xlim()


def test_plot_heatmap_annote_chaque_cellule():
    matrix = pd.DataFrame([[1.0, 0.5], [0.5, 1.0]], index=list("ab"), columns=list("ab"))
    figure = eda.plot_heatmap(matrix, diverging=False, annotate=True)
    textes = [text.get_text() for text in figure.axes[0].texts]
    assert textes == ["1.00", ".50", ".50", "1.00"]
