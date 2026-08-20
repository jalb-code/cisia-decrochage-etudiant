import numpy as np
import pandas as pd

from decrochage_l1.modeling import pipeline
from decrochage_l1.modeling.spec import load_spec

MENTIONS = ("passable", "assez bien", "bien", "tres bien")
FILIERES = (
    "biologie",
    "droit",
    "gestion",
    "informatique",
    "lettres",
    "mathematiques",
    "psychologie",
    "staps",
)
BAC_TYPES = ("general", "technologique", "professionnel")


def gold_frame(n: int = 300) -> pd.DataFrame:
    # Jeu « gold » synthétique : les 16 features retenues + les deux cibles, dtypes numpy.
    rng = np.random.default_rng(0)
    total = rng.integers(5, 20, n)
    rendus = np.minimum(total, rng.integers(0, 20, n))
    retards = np.minimum(rendus, rng.integers(0, 10, n))
    frame = pd.DataFrame(
        {
            "age": rng.integers(17, 25, n).astype(float),
            "taux_presence_pct": rng.uniform(30, 100, n),
            "heures_lms_total": rng.uniform(0, 120, n),
            "retards_rendus": retards.astype(float),
            "nb_devoirs_total": total.astype(float),
            "nb_devoirs_rendus": rendus.astype(float),
            "messages_forum": rng.integers(0, 15, n).astype(float),
            "nb_ue_total": rng.integers(5, 8, n).astype(float),
            "motivation": rng.integers(1, 6, n).astype(float),
            "satisfaction": rng.integers(1, 6, n).astype(float),
            "sentiment_appartenance": rng.integers(1, 6, n).astype(float),
            "mention_bac": rng.choice(MENTIONS, n),
            "filiere": rng.choice(FILIERES, n),
            "bac_type": rng.choice(BAC_TYPES, n),
        }
    )
    frame["taux_rendu"] = frame["nb_devoirs_rendus"] / frame["nb_devoirs_total"]
    frame["ratio_retards"] = frame["retards_rendus"] / frame["nb_devoirs_total"]
    frame["abandon"] = (frame["taux_presence_pct"] < 60).astype(int)
    frame["moyenne_finale"] = np.clip(5 + 0.1 * frame["taux_presence_pct"], 0, 20)
    return frame


def test_load_spec_valeurs_clefs():
    spec = load_spec()
    assert spec.target == "abandon"
    assert spec.target_secondary == "moyenne_finale"
    assert spec.seed == 42
    assert spec.recall_target == 0.8
    assert spec.family_classifier == "logreg"


def test_features_min_reduit_aux_16():
    spec = load_spec()
    feats = spec.features_min(list(gold_frame().columns))
    assert len(feats) == 16
    # filiere/bac_type survivent ; les leurres et proxies retirés par ablation, non.
    assert "filiere" in feats
    assert "groupe_td" not in feats
    assert "etablissement_origine" not in feats


def test_build_classifier_fit_predict():
    spec = load_spec()
    gold = gold_frame()
    feats = spec.features_min(list(gold.columns))
    clf = pipeline.build_classifier(spec, gold, feats)
    clf.fit(gold[feats], gold["abandon"])
    assert list(clf.feature_names_in_) == feats
    proba = clf.predict_proba(gold[feats])[:, 1]
    assert ((proba >= 0) & (proba <= 1)).all()


def test_build_regressor_fit_predict():
    spec = load_spec()
    gold = gold_frame()
    feats = spec.features_min(list(gold.columns))
    reg = pipeline.build_regressor(spec, gold, feats)
    reg.fit(gold[feats], gold["moyenne_finale"])
    pred = reg.predict(gold[feats])
    assert np.isfinite(pred).all()
