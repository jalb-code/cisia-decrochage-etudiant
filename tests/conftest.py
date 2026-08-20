"""Artefact-stub : un modèle factice mais complet, aligné sur le schéma d'entrée réel.

Le stub construit deux pipelines (classification `abandon`, régression `moyenne_finale`) sur
les **14 features d'entrée** de `PredictEtudiantForm` (+ 2 dérivées), une fiche allégée et une
distribution de référence, puis les sérialise via `store` — de quoi exercer entrepôt, API,
explicabilité et dérive exactement comme le fera l'artefact réel, sans le modèle du notebook.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline

from decrochage_l1.modeling.preprocessing import make_preprocessor
from decrochage_l1.serving import store
from decrochage_l1.serving.contract import ModelFacts, OperationalDefaults, ServiceContract

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
MENTIONS = ("passable", "assez bien", "bien", "tres bien")  # ordre ordinal

NUMERIC_INPUT = (
    "age",
    "taux_presence_pct",
    "heures_lms_total",
    "nb_ue_total",
    "nb_devoirs_total",
    "nb_devoirs_rendus",
    "retards_rendus",
    "messages_forum",
    "motivation",
    "satisfaction",
    "sentiment_appartenance",
)
DERIVED = ("taux_rendu", "ratio_retards")
NUMERIC = (*NUMERIC_INPUT, *DERIVED)
CATEGORICAL = ("mention_bac", "filiere", "bac_type")
MODEL_FEATURES = [*NUMERIC, *CATEGORICAL]

THEMES = {
    "taux_presence_pct": "assiduité",
    "nb_devoirs_total": "assiduité",
    "nb_devoirs_rendus": "assiduité",
    "retards_rendus": "assiduité",
    "taux_rendu": "assiduité",
    "ratio_retards": "assiduité",
    "heures_lms_total": "engagement",
    "messages_forum": "engagement",
    "motivation": "ressenti",
    "satisfaction": "ressenti",
    "sentiment_appartenance": "ressenti",
    "age": "parcours",
    "nb_ue_total": "parcours",
    "mention_bac": "parcours",
    "filiere": "parcours",
    "bac_type": "parcours",
}


def _training_frame(rng: np.random.Generator, n: int = 400) -> pd.DataFrame:
    total = rng.integers(5, 20, n)
    rendus = np.minimum(total, rng.integers(0, 20, n))
    retards = np.minimum(rendus, rng.integers(0, 10, n))
    frame = pd.DataFrame(
        {
            "age": rng.integers(17, 25, n),
            "taux_presence_pct": rng.uniform(30, 100, n),
            "heures_lms_total": rng.uniform(0, 120, n),
            "nb_ue_total": rng.integers(5, 8, n),
            "nb_devoirs_total": total,
            "nb_devoirs_rendus": rendus,
            "retards_rendus": retards,
            "messages_forum": rng.integers(0, 15, n),
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
    return frame


def _make_pipeline(estimator) -> Pipeline:
    preprocessor = make_preprocessor(
        numeric=list(NUMERIC),
        ordinal=["mention_bac"],
        onehot=["filiere", "bac_type"],
        ordinal_categories=[list(MENTIONS)],
        onehot_categories=[list(FILIERES), list(BAC_TYPES)],
        scale=True,
    )
    return Pipeline([("prep", preprocessor), ("model", estimator)])


def _contract(reference: pd.DataFrame) -> ServiceContract:
    facts = ModelFacts(
        version="stub-1",
        numeric=NUMERIC,
        categorical=CATEGORICAL,
        themes=THEMES,
        drift_reference=reference,
    )
    defaults = OperationalDefaults(
        threshold=0.16,
        drift_surveillance=0.10,
        drift_alerte=0.25,
        drift_effectif_min=200,
    )
    return ServiceContract(facts=facts, defaults=defaults)


@dataclass
class Stub:
    """Ce qu'un test consomme : le dossier d'artefacts, la fiche, et de quoi forger un dossier."""

    artifacts_dir: Path
    contract: ServiceContract
    training: pd.DataFrame

    def dossier(self, **overrides) -> dict:
        """Un dossier valide (entrée typée propre), surchargeable champ par champ."""
        base = {
            "reference_dossier": "ref-0",
            "age": 19,
            "filiere": "informatique",
            "bac_type": "general",
            "taux_presence_pct": 85.0,
            "heures_lms_total": 40.0,
            "nb_ue_total": 6,
            "nb_devoirs_total": 10,
            "nb_devoirs_rendus": 8,
            "retards_rendus": 1,
            "messages_forum": 3,
            "mention_bac": "bien",
            "motivation": 4.0,
            "satisfaction": 3.0,
            "sentiment_appartenance": 3.0,
        }
        base.update(overrides)
        return base


@pytest.fixture
def stub(tmp_path: Path) -> Stub:
    rng = np.random.default_rng(0)
    training = _training_frame(rng)
    X = training[MODEL_FEATURES]
    # Cible binaire à deux classes garanties : l'assiduité sépare franchement.
    y_abandon = (training["taux_presence_pct"] < 60).astype(int)
    y_moyenne = np.clip(
        5
        + 0.1 * training["taux_presence_pct"]
        + 5 * training["taux_rendu"]
        + rng.normal(0, 1, len(training)),
        0,
        20,
    )

    classifier = _make_pipeline(LogisticRegression(max_iter=1000, random_state=0)).fit(X, y_abandon)
    regressor = _make_pipeline(LinearRegression()).fit(X, y_moyenne)

    contract = _contract(training[MODEL_FEATURES].head(300))
    artifacts_dir = tmp_path / "artifacts"
    store.save_bundle(artifacts_dir, contract=contract, classifier=classifier, regressor=regressor)
    return Stub(artifacts_dir=artifacts_dir, contract=contract, training=training)
