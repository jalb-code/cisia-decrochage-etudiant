import pytest

from conftest import MODEL_FEATURES
from decrochage_l1.serving.store import EntrepotModele


def test_chargement_round_trip(stub):
    entrepot = EntrepotModele()
    entrepot.load(stub.artifacts_dir)
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
