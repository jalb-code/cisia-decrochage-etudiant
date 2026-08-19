"""Artefact-stub : un modèle factice mais complet, pour tester le service sans le vrai §9.

Le stub construit deux pipelines (classification `abandon`, régression `moyenne_finale`),
une fiche cohérente et une distribution de référence, puis les sérialise via `store` — de
quoi exercer entrepôt, validation, explicabilité et API exactement comme le fera l'artefact
réel, sans dépendre du modèle entraîné au notebook.
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
from decrochage_l1.serving.contract import (
    Bound,
    CoherenceRule,
    Exclusion,
    ModelFacts,
    OperationalDefaults,
    ServiceContract,
)

FILIERES = ("biologie", "droit", "informatique", "staps")
NUMERIC = (
    "taux_presence_pct",
    "nb_devoirs_total",
    "nb_devoirs_rendus",
    "retards_rendus",
    "motivation",
    "taux_rendu",
    "ratio_retards",
)
INPUT = (
    "taux_presence_pct",
    "nb_devoirs_total",
    "nb_devoirs_rendus",
    "retards_rendus",
    "motivation",
    "filiere",
)
MODEL_FEATURES = [*NUMERIC, "filiere"]


def _training_frame(rng: np.random.Generator, n: int = 400) -> pd.DataFrame:
    total = rng.integers(5, 20, n)
    rendus = np.minimum(total, rng.integers(0, 20, n))
    retards = np.minimum(rendus, rng.integers(0, 10, n))
    frame = pd.DataFrame(
        {
            "taux_presence_pct": rng.uniform(30, 100, n),
            "nb_devoirs_total": total,
            "nb_devoirs_rendus": rendus,
            "retards_rendus": retards,
            "motivation": rng.integers(1, 6, n),
            "filiere": rng.choice(FILIERES, n),
        }
    )
    frame["taux_rendu"] = frame["nb_devoirs_rendus"] / frame["nb_devoirs_total"]
    frame["ratio_retards"] = frame["retards_rendus"] / frame["nb_devoirs_total"]
    return frame


def _make_pipeline(estimator) -> Pipeline:
    preprocessor = make_preprocessor(
        numeric=list(NUMERIC),
        ordinal=[],
        onehot=["filiere"],
        ordinal_categories=[],
        onehot_categories=[list(FILIERES)],
        scale=True,
    )
    return Pipeline([("prep", preprocessor), ("model", estimator)])


def _contract(reference: pd.DataFrame) -> ServiceContract:
    facts = ModelFacts(
        version="stub-1",
        input_columns=INPUT,
        derived_columns=("taux_rendu", "ratio_retards"),
        numeric=NUMERIC,
        categorical=("filiere",),
        nominal_modalities={"filiere": FILIERES},
        exclusions=(
            Exclusion("moyenne_partiels_s1", "fuite temporelle"),
            Exclusion("sexe", "variable sensible"),
        ),
        themes={
            "taux_presence_pct": "assiduité",
            "nb_devoirs_total": "assiduité",
            "nb_devoirs_rendus": "assiduité",
            "retards_rendus": "assiduité",
            "taux_rendu": "assiduité",
            "ratio_retards": "assiduité",
            "motivation": "ressenti",
            "filiere": "contexte",
        },
        units={"taux_presence_pct": ("%",)},
        drift_reference=reference,
    )
    defaults = OperationalDefaults(
        threshold=0.16,
        bounds={
            "taux_presence_pct": Bound(0, 100),
            "nb_devoirs_total": Bound(1, 50),
            "nb_devoirs_rendus": Bound(0, 50),
            "retards_rendus": Bound(0, 50),
            "motivation": Bound(1, 5),
        },
        coherence=(
            CoherenceRule("nb_devoirs_rendus", "nb_devoirs_total"),
            CoherenceRule("retards_rendus", "nb_devoirs_rendus"),
        ),
        drift_surveillance=0.10,
        drift_alerte=0.25,
        drift_effectif_min=200,
    )
    return ServiceContract(facts=facts, defaults=defaults)


@dataclass
class Stub:
    """Ce qu'un test consomme : le dossier d'artefacts, la fiche, et de quoi forger un dossier."""

    models_dir: Path
    contract: ServiceContract
    training: pd.DataFrame

    def dossier(self, **overrides) -> dict:
        """Un dossier brut valide (écriture « sale » assumée), surchargeable champ par champ."""
        base = {
            "reference_dossier": "ref-0",
            "taux_presence_pct": "85 %",
            "nb_devoirs_total": "10",
            "nb_devoirs_rendus": "8",
            "retards_rendus": "1",
            "motivation": "4",
            "filiere": "Informatique",
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

    contract = _contract(training[[*NUMERIC, "filiere"]].head(300))
    models_dir = tmp_path / "models"
    store.save_bundle(models_dir, contract=contract, classifier=classifier, regressor=regressor)
    return Stub(models_dir=models_dir, contract=contract, training=training)
