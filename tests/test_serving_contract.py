import pandas as pd
import pytest

from decrochage_l1.serving import contract as ct


def _facts() -> ct.ModelFacts:
    return ct.ModelFacts(
        version="test-1",
        input_columns=("taux_presence_pct", "nb_devoirs_total", "nb_devoirs_rendus", "filiere"),
        derived_columns=("taux_rendu",),
        numeric=("taux_presence_pct", "nb_devoirs_total", "nb_devoirs_rendus", "taux_rendu"),
        categorical=("filiere",),
        nominal_modalities={"filiere": ("biologie", "droit", "informatique")},
        exclusions=(ct.Exclusion("moyenne_partiels_s1", "fuite temporelle"),),
        themes={"taux_presence_pct": "assiduité", "taux_rendu": "assiduité"},
    )


def _defaults() -> ct.OperationalDefaults:
    return ct.OperationalDefaults(
        threshold=0.16,
        bounds={
            "taux_presence_pct": ct.Bound(0, 100),
            "nb_devoirs_total": ct.Bound(1, 50),
        },
        coherence=(ct.CoherenceRule("nb_devoirs_rendus", "nb_devoirs_total"),),
        drift_surveillance=0.10,
        drift_alerte=0.25,
        drift_effectif_min=200,
    )


def _contract() -> ct.ServiceContract:
    return ct.ServiceContract(facts=_facts(), defaults=_defaults())


def test_contrat_coherent_valide():
    _contract().validate()  # ne lève pas


def test_bound_contains():
    borne = ct.Bound(0, 100)
    assert borne.contains(0) and borne.contains(100)
    assert not borne.contains(-1) and not borne.contains(101)
    # Grandeur ouverte : pas de maximum, aucune valeur haute rejetée.
    ouverte = ct.Bound(minimum=0)
    assert ouverte.contains(10_000)


def test_coherence_rule_holds():
    regle = ct.CoherenceRule("rendus", "total")
    assert regle.holds({"rendus": 3, "total": 5})
    assert not regle.holds({"rendus": 6, "total": 5})
    # Un champ manquant n'infirme pas la règle.
    assert regle.holds({"rendus": None, "total": 5})


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


def test_borne_sur_colonne_inconnue_refusee():
    defauts = _defaults()
    defauts.bounds["colonne_fantome"] = ct.Bound(0, 1)
    with pytest.raises(ValueError, match="bornes sur des colonnes inconnues"):
        ct.ServiceContract(facts=_facts(), defaults=defauts).validate()


def test_theme_sur_colonne_inconnue_refuse():
    faits = _facts()
    faits.themes["variable_fantome"] = "assiduité"
    with pytest.raises(ValueError, match="thèmes sur des colonnes inconnues"):
        ct.ServiceContract(facts=faits, defaults=_defaults()).validate()


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
