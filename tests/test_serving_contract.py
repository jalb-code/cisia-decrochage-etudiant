import pandas as pd
import pytest

from decrochage_l1.serving import contract as ct
from decrochage_l1.serving import drift


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


def _train_reference() -> pd.DataFrame:
    # Un jeu de référence factice où chaque ligne est un « dossier » cohérent : l'âge croît avec
    # la présence, la filière suit - ce sont ces liaisons entre colonnes qu'on veut détruire.
    return pd.DataFrame(
        {
            "age": [18, 19, 20, 21, 22, 23, 24, 25],
            "taux_presence_pct": [95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0],
            "filiere": ["droit", "droit", "staps", "staps", "info", "info", "bio", "bio"],
        }
    )


def test_reference_derive_marginales_intactes():
    # D45 : le mélange par colonne conserve la distribution de chaque variable...
    original = _train_reference()
    reference = ct.build_drift_reference(original, seed=42)
    for colonne in original.columns:
        pd.testing.assert_series_equal(
            original[colonne].value_counts().sort_index(),
            reference[colonne].value_counts().sort_index(),
            check_names=False,
        )


def test_reference_derive_ne_mesure_aucune_derive():
    # ...donc la dérive d'une variable contre sa propre référence mélangée est nulle.
    original = _train_reference()
    reference = ct.build_drift_reference(original, seed=42)
    psi_num = drift.population_stability_index(reference["age"], original["age"])
    psi_cat = drift.population_stability_index_categorical(
        reference["filiere"], original["filiere"]
    )
    assert psi_num == pytest.approx(0.0, abs=1e-9)
    assert psi_cat == pytest.approx(0.0, abs=1e-9)


def test_reference_derive_detruit_la_structure_jointe():
    # Aucune ligne « dossier » ne survit : le mélange casse l'alignement entre colonnes.
    original = _train_reference()
    reference = ct.build_drift_reference(original, seed=42)
    jointes = original.merge(reference, how="inner", on=list(original.columns))
    assert len(jointes) == 0


def test_reference_derive_reproductible():
    # Graine fixe : deux constructions donnent la même référence (traçabilité de l'artefact).
    original = _train_reference()
    pd.testing.assert_frame_equal(
        ct.build_drift_reference(original, seed=42),
        ct.build_drift_reference(original, seed=42),
    )
