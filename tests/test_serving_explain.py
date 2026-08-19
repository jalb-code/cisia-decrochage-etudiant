import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from decrochage_l1.modeling.preprocessing import make_preprocessor
from decrochage_l1.serving import explain

RNG = np.random.default_rng(0)


@pytest.fixture
def pipeline_et_donnees():
    """Un pipeline logistique fit sur un jeu synthétique : 2 numériques + 1 nominale (a/b/c)."""
    n = 300
    data = pd.DataFrame(
        {
            "n1": RNG.normal(size=n),
            "n2": RNG.normal(size=n),
            "c1": RNG.choice(["a", "b", "c"], size=n),
        }
    )
    # Cible dépendant réellement des variables, pour des coefficients non nuls.
    logit = 1.5 * data["n1"] - 0.8 * data["n2"] + data["c1"].map({"a": 1.0, "b": 0.0, "c": -1.0})
    y = (logit + RNG.normal(scale=0.3, size=n) > 0).astype(int)

    preprocessor = make_preprocessor(
        numeric=["n1", "n2"],
        ordinal=[],
        onehot=["c1"],
        ordinal_categories=[],
        onehot_categories=[["a", "b", "c"]],
        scale=True,
    )
    pipeline = Pipeline(
        [("prep", preprocessor), ("model", LogisticRegression(max_iter=1000, random_state=0))]
    )
    pipeline.fit(data, y)
    return pipeline, data


def test_source_columns_replie_le_onehot(pipeline_et_donnees):
    pipeline, _ = pipeline_et_donnees
    sources = explain.source_columns(explain._column_transformer(pipeline))
    # 2 numériques (1:1) + 3 modalités de c1 (dépliées) == 5 colonnes de sortie.
    assert sources == ["n1", "n2", "c1", "c1", "c1"]


def test_logcote_reconstituee_egale_decision_function(pipeline_et_donnees):
    pipeline, data = pipeline_et_donnees
    ligne = data.iloc[[0]]
    contrib = explain.contributions(pipeline, ligne)
    attendu = float(pipeline.decision_function(ligne)[0])
    # La décomposition est EXACTE, pas approchée : base + Σ contributions == log-cote.
    assert contrib.total_logit == pytest.approx(attendu, abs=1e-9)


def test_probabilite_egale_predict_proba(pipeline_et_donnees):
    pipeline, data = pipeline_et_donnees
    ligne = data.iloc[[0]]
    contrib = explain.contributions(pipeline, ligne)
    attendu = float(pipeline.predict_proba(ligne)[0, 1])
    assert contrib.probability == pytest.approx(attendu, abs=1e-9)


def test_agregation_par_variable_sans_perte(pipeline_et_donnees):
    pipeline, data = pipeline_et_donnees
    contrib = explain.contributions(pipeline, data.iloc[[0]])
    somme_variables = sum(contrib.by_variable.values())
    assert somme_variables == pytest.approx(contrib.total_logit - contrib.base_logit, abs=1e-9)
    assert set(contrib.by_variable) == {"n1", "n2", "c1"}


def test_agregation_par_theme_exacte(pipeline_et_donnees):
    pipeline, data = pipeline_et_donnees
    themes = {"n1": "engagement", "n2": "engagement", "c1": "contexte"}
    contrib = explain.contributions(pipeline, data.iloc[[0]], themes=themes)
    assert set(contrib.by_theme) == {"engagement", "contexte"}
    # La somme des thèmes égale la somme des variables : agrégation exhaustive.
    assert sum(contrib.by_theme.values()) == pytest.approx(
        sum(contrib.by_variable.values()), abs=1e-9
    )


def test_variable_sans_theme_declare_va_dans_ungrouped(pipeline_et_donnees):
    pipeline, data = pipeline_et_donnees
    contrib = explain.contributions(pipeline, data.iloc[[0]], themes={"n1": "engagement"})
    # n2 et c1 non déclarés retombent dans le thème d'accueil, rien n'est perdu.
    assert explain.UNGROUPED in contrib.by_theme
    assert sum(contrib.by_theme.values()) == pytest.approx(
        sum(contrib.by_variable.values()), abs=1e-9
    )


def test_refuse_plusieurs_lignes(pipeline_et_donnees):
    pipeline, data = pipeline_et_donnees
    with pytest.raises(ValueError, match="dossier unique"):
        explain.contributions(pipeline, data.iloc[:3])
