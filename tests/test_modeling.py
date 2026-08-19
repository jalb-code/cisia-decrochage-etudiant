"""Tests de la modélisation - protocole, préprocesseur, familles, évaluation, ablation.

Les modules portent le *verbe* : on vérifie leur mécanique (stratification, imputation,
encodage déclaré, indépendance des pipelines, calcul des métriques), pas les jugements
métier - qui vivent au notebook. Données synthétiques minimales, jamais le vrai jeu.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.pipeline import Pipeline

from decrochage_l1.data import preparation
from decrochage_l1.modeling import (
    ablation,
    evaluation,
    families,
    preprocessing,
    protocol,
    threshold,
    tuning,
)

# --- Protocole : split scellé et validation croisée ---------------------------


def _jeu_desequilibre() -> pd.DataFrame:
    """100 lignes, 30 % de positifs, une colonne 'extra' pour vérifier qu'on ne perd rien."""
    cible = [1] * 30 + [0] * 70
    return pd.DataFrame({"abandon": cible, "x": range(100), "extra": ["a"] * 100})


def test_make_split_preserve_le_taux_de_positifs():
    """La stratification garde le déséquilibre identique en train et test."""
    train, test = protocol.make_split(_jeu_desequilibre(), "abandon", test_size=0.2, seed=0)
    assert (len(train), len(test)) == (80, 20)
    assert train["abandon"].mean() == pytest.approx(0.30)
    assert test["abandon"].mean() == pytest.approx(0.30)


def test_make_split_scelle_le_test_sans_recouvrement():
    """Aucune ligne ne peut être à la fois au train et au test."""
    df = _jeu_desequilibre()
    train, test = protocol.make_split(df, "abandon", test_size=0.2, seed=0)
    assert set(train["x"]) & set(test["x"]) == set()
    assert set(train["x"]) | set(test["x"]) == set(df["x"])
    assert "extra" in train.columns  # toutes les colonnes conservées (protégées incluses)


def test_make_split_est_reproductible():
    df = _jeu_desequilibre()
    a, _ = protocol.make_split(df, "abandon", seed=0)
    b, _ = protocol.make_split(df, "abandon", seed=0)
    pd.testing.assert_frame_equal(a, b)


def test_make_cv_stratifie_ou_non_selon_la_cible():
    assert isinstance(protocol.make_cv(stratified=True), StratifiedKFold)
    assert isinstance(protocol.make_cv(stratified=False), KFold)
    cv = protocol.make_cv(n_splits=5, seed=0)
    assert cv.n_splits == 5 and cv.shuffle is True


# --- Préprocesseur : imputation, encodage déclaré, scaling --------------------


def _preproc(scale: bool) -> object:
    return preprocessing.make_preprocessor(
        numeric=["num"],
        ordinal=["mention_bac"],
        onehot=["filiere"],
        ordinal_categories=[list(preparation.ORDINAL_MODALITIES["mention_bac"])],
        onehot_categories=[list(preparation.NOMINAL_MODALITIES["filiere"])],
        scale=scale,
    )


def test_resolve_categories_ajoute_les_modalites_inedites_apres_les_declarees():
    """Nominal : les déclarées d'abord (position stable), toute inédite du jeu ensuite."""
    declared = {"filiere": ("droit", "staps")}
    data = pd.DataFrame({"filiere": ["droit", "philo", "philo"]})
    categories, extras = preprocessing.resolve_categories(declared, data, ["filiere"])
    assert categories[0] == ["droit", "staps", "philo"]
    assert extras == {"filiere": ["philo"]}  # l'inédite est signalée pour contrôle humain


def test_resolve_categories_garde_une_modalite_declaree_absente_du_jeu():
    """Une modalité rare déclarée garde sa colonne même si le jeu ne la contient pas."""
    declared = {"filiere": ("droit", "staps")}
    data = pd.DataFrame({"filiere": ["droit", "droit"]})
    categories, extras = preprocessing.resolve_categories(declared, data, ["filiere"])
    assert categories[0] == ["droit", "staps"]
    assert extras == {}


def test_resolve_categories_sans_extend_signale_sans_inserer():
    """Ordinal : une modalité hors échelle n'a pas d'ordre - signalée, jamais insérée."""
    declared = {"mention_bac": ("passable", "bien")}
    data = pd.DataFrame({"mention_bac": ["bien", "excellent"]})
    categories, extras = preprocessing.resolve_categories(
        declared, data, ["mention_bac"], extend=False
    )
    assert categories[0] == ["passable", "bien"]
    assert extras == {"mention_bac": ["excellent"]}


def test_to_numpy_dtypes_convertit_les_nullables_en_numpy():
    """Int64/string nullables → float64/object, pd.NA → np.nan (sklearn ne bute plus)."""
    df = pd.DataFrame(
        {
            "n": pd.array([1, None, 3], dtype="Int64"),
            "s": pd.array(["a", None, "b"], dtype="string"),
        }
    )
    out = preprocessing.to_numpy_dtypes(df)
    assert out["n"].dtype == "float64"
    assert out["s"].dtype == object
    assert np.isnan(out["n"].to_numpy(dtype=float)).sum() == 1
    assert out["s"].isna().sum() == 1


def _petit_jeu() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "num": [1.0, 2.0, np.nan, 4.0],
            "mention_bac": ["passable", "tres bien", None, "bien"],
            "filiere": ["droit", "staps", "droit", "gestion"],
        }
    )


def test_numerique_impute_la_mediane_sans_scaling():
    """Le manquant numérique prend la médiane des observés (2.0), l'absence n'y vaut pas 0."""
    out = _preproc(scale=False).fit_transform(_petit_jeu())
    assert out[2, 0] == pytest.approx(2.0)  # médiane de [1, 2, 4]


def test_scaling_centre_reduit_la_colonne_numerique():
    """Avec scaling, la colonne numérique est centrée (moyenne ≈ 0)."""
    out = _preproc(scale=True).fit_transform(_petit_jeu())
    assert out[:, 0].mean() == pytest.approx(0.0, abs=1e-9)


def test_ordinal_respecte_l_ordre_declare():
    """passable < bien < tres bien encodés 0 < 2 < 3 ; le manquant prend la médiane."""
    out = _preproc(scale=False).fit_transform(_petit_jeu())
    ordinal_col = out[:, 1]
    assert ordinal_col[0] == pytest.approx(0.0)  # passable
    assert ordinal_col[1] == pytest.approx(3.0)  # tres bien
    assert ordinal_col[3] == pytest.approx(2.0)  # bien


def test_onehot_deploie_le_vocabulaire_declare_meme_absent_du_jeu():
    """Les 8 filières déclarées font 8 colonnes, même celles absentes de l'échantillon."""
    preproc = _preproc(scale=False).fit(_petit_jeu())
    noms = [n for n in preproc.get_feature_names_out() if n.startswith("cat__")]
    assert len(noms) == len(preparation.NOMINAL_MODALITIES["filiere"])


def test_onehot_ignore_une_modalite_inconnue():
    """handle_unknown='ignore' : une modalité hors vocabulaire ne lève rien, tout à zéro."""
    preproc = _preproc(scale=False).fit(_petit_jeu())
    inconnu = pd.DataFrame({"num": [1.0], "mention_bac": ["bien"], "filiere": ["xxx"]})
    transforme = preproc.transform(inconnu)
    colonnes_cat = [
        i for i, n in enumerate(preproc.get_feature_names_out()) if n.startswith("cat__")
    ]
    assert transforme[0, colonnes_cat].sum() == pytest.approx(0.0)


def test_etablissement_absent_devient_la_modalite_inconnu():
    """Un manquant nominal prend la modalité d'absence explicite, pas un mode (D09)."""
    preproc = preprocessing.make_preprocessor(
        numeric=[],
        ordinal=[],
        onehot=["etablissement_origine"],
        ordinal_categories=[],
        onehot_categories=[list(preparation.NOMINAL_MODALITIES["etablissement_origine"])],
        scale=False,
    )
    data = pd.DataFrame({"etablissement_origine": ["cfa", None]})
    out = preproc.fit_transform(data)
    noms = list(preproc.get_feature_names_out())
    col_inconnu = noms.index("cat__etablissement_origine_inconnu")
    assert out[1, col_inconnu] == pytest.approx(1.0)


# --- Familles : pipelines indépendants ----------------------------------------


def test_build_classifiers_rend_trois_pipelines_distincts():
    preproc = _preproc(scale=True)
    clf = families.build_classifiers(preproc_linear=preproc, preproc_tree=_preproc(False), seed=0)
    assert set(clf) == {"logreg", "random_forest", "xgboost"}
    assert all(isinstance(p, Pipeline) for p in clf.values())
    # chaque pipeline a sa PROPRE copie du préprocesseur (aucun partage d'objet ajustable)
    preprocs = [p.named_steps["prep"] for p in clf.values()]
    assert len({id(p) for p in preprocs}) == 3


def test_build_regressors_rend_les_trois_familles_de_regression():
    clf = families.build_regressors(preproc_linear=_preproc(True), preproc_tree=_preproc(False))
    assert set(clf) == {"ridge", "random_forest", "gradient_boosting"}


# --- Évaluation : métriques ---------------------------------------------------


def test_classification_metrics_sur_un_classement_parfait():
    """Un score qui ordonne parfaitement donne une ROC-AUC de 1."""
    y = pd.Series([0, 0, 1, 1])
    proba = np.array([0.1, 0.2, 0.8, 0.9])
    m = evaluation.classification_metrics(y, proba)
    assert m["roc_auc"] == pytest.approx(1.0)
    assert m["pr_auc"] == pytest.approx(1.0)
    assert 0.0 <= m["brier"] <= 1.0


def test_cv_scores_rend_un_score_par_pli():
    """Autant de scores que de plis, chacun dans [0, 1] pour une AUC."""
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"x": rng.normal(size=120)})
    y = pd.Series((X["x"] > 0).astype(int))
    preproc = preprocessing.make_preprocessor(
        numeric=["x"],
        ordinal=[],
        onehot=[],
        ordinal_categories=[],
        onehot_categories=[],
        scale=True,
    )
    pipe = families.build_classifiers(preproc_linear=preproc, preproc_tree=preproc)["logreg"]
    scores = evaluation.cv_scores(pipe, X, y, protocol.make_cv(n_splits=4, seed=0))
    assert scores.shape == (4,)
    assert ((scores >= 0) & (scores <= 1)).all()


def test_regression_metrics_sur_une_prediction_parfaite():
    y = pd.Series([10.0, 12.0, 14.0])
    m = evaluation.regression_metrics(y, np.array([10.0, 12.0, 14.0]))
    assert m["mae"] == pytest.approx(0.0)
    assert m["rmse"] == pytest.approx(0.0)
    assert m["r2"] == pytest.approx(1.0)


# --- Ablation : coût du retrait ----------------------------------------------


def test_ablate_liste_les_scenarios_et_l_ecart_au_complet():
    """Chaque bloc donne un scénario ; le complet est la référence (écart nul)."""
    rng = np.random.default_rng(0)
    n = 200
    X = pd.DataFrame(
        {
            "signal": rng.normal(size=n),
            "bruit_a": rng.normal(size=n),
            "bruit_b": rng.normal(size=n),
        }
    )
    y = pd.Series((X["signal"] > 0).astype(int))

    def build_pipeline(features):
        preproc = preprocessing.make_preprocessor(
            numeric=list(features),
            ordinal=[],
            onehot=[],
            ordinal_categories=[],
            onehot_categories=[],
            scale=True,
        )
        return families.build_classifiers(preproc_linear=preproc, preproc_tree=preproc, seed=0)[
            "logreg"
        ]

    cv = protocol.make_cv(n_splits=3, seed=0)
    table = ablation.ablate(build_pipeline, X, y, {"bruit": ["bruit_a", "bruit_b"]}, cv)

    assert list(table.index) == ["complet", "sans bruit", "minimisé"]
    assert table.loc["complet", "d_roc_auc"] == pytest.approx(0.0)
    assert table.loc["complet", "n_features"] == 3
    assert table.loc["sans bruit", "n_features"] == 1


def test_ablate_regression_rend_mae_rmse_r2_et_applique_le_postprocess():
    """Régression : métriques MAE/RMSE/R² par scénario, et `postprocess` (ex. clip) appliqué."""
    rng = np.random.default_rng(0)
    n = 200
    X = pd.DataFrame({"signal": rng.normal(size=n), "bruit": rng.normal(size=n)})
    y = pd.Series(5 * X["signal"] + rng.normal(size=n))

    def build_pipeline(features):
        preproc = preprocessing.make_preprocessor(
            numeric=list(features),
            ordinal=[],
            onehot=[],
            ordinal_categories=[],
            onehot_categories=[],
            scale=True,
        )
        return families.build_regressors(preproc_linear=preproc, preproc_tree=preproc)["ridge"]

    cv = protocol.make_cv(n_splits=3, seed=0, stratified=False)
    table = ablation.ablate_regression(build_pipeline, X, y, {"bruit": ["bruit"]}, cv)
    assert list(table.index) == ["complet", "sans bruit", "minimisé"]
    assert {"mae", "rmse", "r2", "d_mae", "d_rmse", "d_r2"} <= set(table.columns)
    assert table.loc["complet", "d_mae"] == pytest.approx(0.0)

    # postprocess appliqué : forcer toutes les prédictions à 0 → MAE = moyenne des |y|
    force_zero = ablation.ablate_regression(
        build_pipeline, X, y, {"bruit": ["bruit"]}, cv, postprocess=lambda p: p.clip(0, 0)
    )
    assert force_zero.loc["complet", "mae"] == pytest.approx(float(y.abs().mean()), rel=1e-6)


# --- Réglage des hyperparamètres : recherche Optuna bornée, avec pruning ---------


def test_optuna_search_respecte_le_budget_et_rend_les_meilleurs_parametres():
    """La recherche tient le budget `n_trials`, renvoie un jeu de paramètres et l'étude."""
    rng = np.random.default_rng(0)
    n = 200
    X = pd.DataFrame({"x": rng.normal(size=n)})
    # cible linéairement séparable pour que le meilleur C soit discriminable
    y = pd.Series((X["x"] + rng.normal(scale=0.3, size=n) > 0).astype(int))

    def build_pipeline(params):
        preproc = preprocessing.make_preprocessor(
            numeric=["x"],
            ordinal=[],
            onehot=[],
            ordinal_categories=[],
            onehot_categories=[],
            scale=True,
        )
        pipe = families.build_classifiers(preproc_linear=preproc, preproc_tree=preproc, seed=0)[
            "logreg"
        ]
        return pipe.set_params(model__C=params["C"])

    def suggest(trial):
        return {"C": trial.suggest_float("C", 1e-2, 1e2, log=True)}

    cv = protocol.make_cv(n_splits=3, seed=0)
    best, study = tuning.optuna_search(
        build_pipeline, suggest, X, y, cv, scoring="roc_auc", n_trials=8, seed=0
    )
    assert "C" in best
    assert len(study.trials) == 8
    assert 0.0 <= tuning.pruned_ratio(study) <= 1.0


def test_optuna_search_est_reproductible_a_seed_fixe():
    """Même seed, même meilleur paramètre - la recherche est rejouable."""
    rng = np.random.default_rng(1)
    X = pd.DataFrame({"x": rng.normal(size=150)})
    y = pd.Series((X["x"] > 0).astype(int))

    def build_pipeline(params):
        preproc = preprocessing.make_preprocessor(
            numeric=["x"],
            ordinal=[],
            onehot=[],
            ordinal_categories=[],
            onehot_categories=[],
            scale=True,
        )
        pipe = families.build_classifiers(preproc_linear=preproc, preproc_tree=preproc, seed=0)[
            "logreg"
        ]
        return pipe.set_params(model__C=params["C"])

    def suggest(trial):
        return {"C": trial.suggest_float("C", 1e-2, 1e2, log=True)}

    cv = protocol.make_cv(n_splits=3, seed=0)
    a, _ = tuning.optuna_search(
        build_pipeline, suggest, X, y, cv, scoring="roc_auc", n_trials=6, seed=0
    )
    b, _ = tuning.optuna_search(
        build_pipeline, suggest, X, y, cv, scoring="roc_auc", n_trials=6, seed=0
    )
    assert a["C"] == pytest.approx(b["C"])


# --- Cache de réglage : exécution rapide sans relancer la recherche --------------


def test_cached_search_calcule_puis_persiste_a_la_premiere_passe(tmp_path):
    """Cache absent : on calcule, on écrit le fichier, on renvoie le résultat."""
    chemin = tmp_path / "cache.json"
    appels = []

    def compute():
        appels.append(1)
        return {"C": 0.1}

    resultat = tuning.cached_search(chemin, "logreg", compute, use_cache=False)
    assert resultat == {"C": 0.1}
    assert len(appels) == 1
    assert chemin.exists()
    assert tuning.load_cache(chemin)["logreg"] == {"C": 0.1}


def test_cached_search_recharge_sans_recalculer_quand_le_cache_existe(tmp_path):
    """Cache présent + use_cache : on renvoie la valeur stockée sans rappeler compute."""
    chemin = tmp_path / "cache.json"
    tuning.cached_search(chemin, "logreg", lambda: {"C": 0.1}, use_cache=False)

    def compute_interdit():
        raise AssertionError("compute ne doit pas être rappelé quand le cache sert")

    resultat = tuning.cached_search(chemin, "logreg", compute_interdit, use_cache=True)
    assert resultat == {"C": 0.1}


def test_cached_search_recalcule_si_la_cle_manque_meme_en_mode_cache(tmp_path):
    """use_cache mais clé absente : repli sûr, on calcule et on complète le cache."""
    chemin = tmp_path / "cache.json"
    tuning.cached_search(chemin, "logreg", lambda: {"C": 0.1}, use_cache=False)
    resultat = tuning.cached_search(chemin, "foret", lambda: {"n": 300}, use_cache=True)
    assert resultat == {"n": 300}
    assert set(tuning.load_cache(chemin)) == {"logreg", "foret"}


# --- Seuil de décision : table de scénarios et politiques de choix ---------------


def _scores_ordonnes():
    """40 lignes : probabilités croissantes, positifs concentrés dans le haut du classement."""
    proba = np.linspace(0.01, 0.99, 40)
    y = pd.Series((proba >= 0.6).astype(int))  # 16 positifs, les plus hautes probas
    return y, proba


def test_threshold_table_compte_alertes_rappel_et_precision():
    """La table donne volume d'alertes, part de promo et arbitrage rappel/précision cohérents."""
    y, proba = _scores_ordonnes()
    table = threshold.threshold_table(y, proba, thresholds=np.array([0.3, 0.6, 0.9]))
    assert list(table.columns) == [
        "rappel",
        "precision",
        "f2",
        "n_alertes",
        "tp",
        "n_FN",
        "pct_promo",
    ]
    # seuil 0.6 : signale exactement les positifs → rappel, précision et F2 parfaits
    assert table.loc[0.6, "rappel"] == pytest.approx(1.0)
    assert table.loc[0.6, "precision"] == pytest.approx(1.0)
    assert table.loc[0.6, "f2"] == pytest.approx(1.0)
    assert table.loc[0.6, "pct_promo"] == pytest.approx(table.loc[0.6, "n_alertes"] / len(y))
    # seuil plus bas → plus d'alertes, rappel maintenu, précision moindre
    assert table.loc[0.3, "n_alertes"] > table.loc[0.6, "n_alertes"]
    assert table.loc[0.3, "precision"] < table.loc[0.6, "precision"]


def test_pick_threshold_plancher_de_rappel():
    """Le seuil retenu garantit le rappel cible sur les probabilités fournies."""
    y, proba = _scores_ordonnes()
    seuil = threshold.pick_threshold(y, proba, recall_target=0.80)
    pred = proba >= seuil
    rappel = int(np.sum(pred & (np.asarray(y) == 1))) / int(np.asarray(y).sum())
    assert rappel >= 0.80


def test_pick_threshold_capacite_en_nombre():
    """Une capacité de N signale exactement N étudiants."""
    y, proba = _scores_ordonnes()
    seuil = threshold.pick_threshold(y, proba, capacity_n=10)
    assert int(np.sum(proba >= seuil)) == 10


def test_pick_threshold_exige_un_seul_critere():
    y, proba = _scores_ordonnes()
    with pytest.raises(ValueError):
        threshold.pick_threshold(y, proba)
    with pytest.raises(ValueError):
        threshold.pick_threshold(y, proba, recall_target=0.8, capacity_n=5)


def test_plot_confusion_rend_des_comptes_coherents():
    """La matrice affiche 4 cases dont la somme = effectif, et aucun FN à seuil bas."""
    import matplotlib

    matplotlib.use("Agg")
    y, proba = _scores_ordonnes()
    ax = evaluation.plot_confusion(y, proba, threshold=0.05)
    # chaque annotation vaut "TYPE\ncompte" (ex. "FN\n0") ; on relit le compte
    cases = [int(t.get_text().split("\n")[-1]) for t in ax.texts]
    assert sum(cases) == len(y)  # chaque étudiant tombe dans une case et une seule
    assert {t.get_text().split("\n")[0] for t in ax.texts} == {"TN", "FP", "FN", "TP"}
    # seuil très bas → tout le monde signalé → aucun décrocheur manqué (FN = 0)
    pred = np.asarray(proba) >= 0.05
    fn = int(np.sum(~pred & (np.asarray(y) == 1)))
    assert fn == 0
