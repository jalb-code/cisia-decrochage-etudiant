import numpy as np
import pandas as pd

from decrochage_l1.serving import drift

RNG = np.random.default_rng(0)

SEUILS = {"seuil_surveillance": 0.10, "seuil_alerte": 0.25, "effectif_min": 200}


def test_psi_nul_quand_distributions_identiques():
    echantillon = RNG.normal(size=5000)
    # Même distribution (deux tirages de la même loi) : PSI proche de zéro.
    assert drift.population_stability_index(echantillon, RNG.normal(size=5000)) < 0.01


def test_psi_grand_quand_distribution_decalee():
    reference = RNG.normal(loc=0, size=5000)
    decalee = RNG.normal(loc=2, size=5000)  # translation de 2 écarts-types
    assert drift.population_stability_index(reference, decalee) > 0.25


def test_psi_reference_constante_vaut_zero():
    # Une référence sans variance n'a aucun bac exploitable : convention à 0, pas d'erreur.
    assert drift.population_stability_index([5.0] * 100, [5.0, 6.0, 7.0]) == 0.0


def test_psi_categoriel_detecte_bascule_de_modalites():
    reference = ["a"] * 700 + ["b"] * 300
    courante = ["a"] * 300 + ["b"] * 700  # proportions inversées
    assert drift.population_stability_index_categorical(reference, courante) > 0.25


def test_ks_via_scipy_disponible():
    from scipy.stats import ks_2samp

    proche = ks_2samp(RNG.normal(size=2000), RNG.normal(size=2000))
    loin = ks_2samp(RNG.normal(loc=0, size=2000), RNG.normal(loc=3, size=2000))
    assert proche.pvalue > 0.01
    assert loin.pvalue < 0.01


def _campagne(n: int, loc: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame(
        {"x": RNG.normal(loc=loc, size=n), "filiere": RNG.choice(["a", "b"], size=n)}
    )


def test_campagne_non_mesurable_sous_effectif_minimal():
    reference = _campagne(1000)
    petite = _campagne(50)
    bilan = drift.assess(reference, petite, numeric=["x"], **SEUILS)
    assert bilan.mesurable is False
    assert bilan.motif is not None and "50" in bilan.motif
    assert bilan.variables == ()


def test_campagne_stable_quand_meme_population():
    reference = _campagne(2000)
    courante = _campagne(2000)
    bilan = drift.assess(reference, courante, numeric=["x"], categorical=["filiere"], **SEUILS)
    assert bilan.mesurable is True
    assert bilan.verdict == drift.STABLE


def test_campagne_en_alerte_quand_variable_derive():
    reference = _campagne(2000, loc=0.0)
    courante = _campagne(2000, loc=2.0)  # x fortement décalé
    bilan = drift.assess(reference, courante, numeric=["x"], **SEUILS)
    assert bilan.verdict == drift.ALERTE
    assert bilan.psi_max >= SEUILS["seuil_alerte"]
    # La variable dérivée porte le déplacement en écarts-types, du bon ordre de grandeur.
    assert bilan.variables[0].variable == "x"
    assert bilan.variables[0].shift_std is not None and bilan.variables[0].shift_std > 1.5
