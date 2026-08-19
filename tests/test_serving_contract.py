import pandas as pd
import pytest

from decrochage_l1.serving import contract as ct


def _facts() -> ct.ModelFacts:
    return ct.ModelFacts(
        version="test-1",
        numeric=("taux_presence_pct", "taux_rendu"),
        categorical=("filiere",),
        themes={"taux_presence_pct": "assiduité", "taux_rendu": "assiduité"},
    )


def _defaults() -> ct.OperationalDefaults:
    return ct.OperationalDefaults(
        threshold=0.16,
        drift_surveillance=0.10,
        drift_alerte=0.25,
        drift_effectif_min=200,
    )


def _contract() -> ct.ServiceContract:
    return ct.ServiceContract(facts=_facts(), defaults=_defaults())


def test_contrat_coherent_valide():
    _contract().validate()  # ne lève pas


def test_round_trip_joblib(tmp_path):
    reference = pd.DataFrame({"taux_presence_pct": [80.0, 90.0], "filiere": ["droit", "biologie"]})
    original = _contract()
    original.facts.drift_reference = reference
    chemin = tmp_path / "fiche.joblib"
    ct.save(original, chemin)
    recharge = ct.load(chemin)
    assert recharge.facts.version == "test-1"
    assert recharge.defaults.threshold == 0.16
    pd.testing.assert_frame_equal(recharge.facts.drift_reference, reference)


def test_seuil_hors_bornes_refuse():
    defauts = _defaults()
    defauts.threshold = 1.4
    with pytest.raises(ValueError, match="seuil hors"):
        ct.ServiceContract(facts=_facts(), defaults=defauts).validate()


def test_seuils_de_derive_non_ordonnes_refuses():
    defauts = _defaults()
    defauts.drift_surveillance, defauts.drift_alerte = 0.30, 0.10
    with pytest.raises(ValueError, match="seuils de dérive non ordonnés"):
        ct.ServiceContract(facts=_facts(), defaults=defauts).validate()


def test_effectif_min_non_positif_refuse():
    defauts = _defaults()
    defauts.drift_effectif_min = 0
    with pytest.raises(ValueError, match="effectif minimal non positif"):
        ct.ServiceContract(facts=_facts(), defaults=defauts).validate()
