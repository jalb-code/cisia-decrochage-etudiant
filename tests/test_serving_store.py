import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from conftest import MODEL_FEATURES, _make_pipeline
from decrochage_l1.serving import store
from decrochage_l1.serving.store import EntrepotModele


def test_chargement_round_trip(stub):
    entrepot = EntrepotModele()
    entrepot.load(stub.models_dir)
    assert entrepot.ready is True
    assert entrepot.error is None
    assert entrepot.bundle.contract.facts.version == "stub-1"
    # Le classifieur chargé produit bien une probabilité.
    X = stub.training[MODEL_FEATURES].head(3)
    proba = entrepot.bundle.classifier.predict_proba(X)[:, 1]
    assert ((proba >= 0) & (proba <= 1)).all()


def test_chargement_dossier_absent_memorise_l_erreur_sans_lever(tmp_path):
    entrepot = EntrepotModele()
    entrepot.load(tmp_path / "inexistant")  # ne lève pas
    assert entrepot.ready is False
    assert entrepot.error is not None
    with pytest.raises(RuntimeError, match="indisponible"):
        _ = entrepot.bundle


def test_refus_de_servir_un_modele_qui_fuite(stub, tmp_path):
    # Un modèle entraîné en incluant une colonne interdite par la fiche (`sexe`) : refusé.
    rng = np.random.default_rng(1)
    training = stub.training.copy()
    training["sexe"] = rng.choice(["f", "h"], len(training))
    X_leak = training[[*MODEL_FEATURES, "sexe"]]  # `sexe` entre dans feature_names_in_
    y = (training["taux_presence_pct"] < 60).astype(int)
    classifier_leak = _make_pipeline(LogisticRegression(max_iter=1000, random_state=0)).fit(
        X_leak, y
    )

    # Le contrôle anti-fuite précède l'écriture du régresseur : celui-ci n'est jamais atteint.
    with pytest.raises(ValueError, match="interdites"):
        store.save_bundle(
            tmp_path / "leak",
            contract=stub.contract,
            classifier=classifier_leak,
            regressor=Pipeline([("noop", LogisticRegression())]),
        )
