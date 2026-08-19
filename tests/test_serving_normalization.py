"""Tests d'ANTI-DIVERGENCE : la conformation du service doit égaler celle de la préparation.

Le service ré-orchestre la conformation (Option A) à partir de la fiche ; ces tests
garantissent que, sur les mêmes entrées, il produit exactement ce que produit
`preparation.conform` (écriture) et `build_gold` (dérivées). Ils casseraient si l'un des
deux côtés changeait sans l'autre — c'est là leur raison d'être.
"""

import pandas as pd

from decrochage_l1.data import preparation
from decrochage_l1.serving import normalization
from decrochage_l1.serving.contract import ModelFacts

COLONNES = (
    "taux_presence_pct",
    "nb_devoirs_total",
    "nb_devoirs_rendus",
    "retards_rendus",
    "filiere",
)


def _raw() -> pd.DataFrame:
    """Un lot volontairement « sale » : « % », virgule décimale, casse et espaces de bord."""
    return pd.DataFrame(
        {
            "taux_presence_pct": ["85,0 %", "77.5%", " 90 %", ""],
            "nb_devoirs_total": ["10", "12", "8", "9"],
            "nb_devoirs_rendus": ["8", "12", "7", "9"],
            "retards_rendus": ["1", "0", "2", "0"],
            "filiere": ["Informatique", " DROIT ", "Biologie", "informatique"],
        }
    )


def _profile() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "colonne": list(COLONNES),
            "type_semantique": ["decimal", "entier", "entier", "entier", "categorielle"],
        }
    )


def _facts() -> ModelFacts:
    return ModelFacts(
        version="anti-divergence",
        input_columns=COLONNES,
        derived_columns=("taux_rendu", "ratio_retards"),
        numeric=("taux_presence_pct", "nb_devoirs_total", "nb_devoirs_rendus", "retards_rendus"),
        categorical=("filiere",),
        nominal_modalities={"filiere": ("biologie", "droit", "informatique")},
        exclusions=(),
        themes={},
        units={"taux_presence_pct": ("%",)},  # déclarée, comme detect_units la mesurerait
    )


def test_conformation_numerique_egale_preparation():
    raw = _raw()
    attendu = preparation.conform(raw, _profile())
    service = normalization.conform_frame(raw, _facts())
    for colonne in ("taux_presence_pct", "nb_devoirs_total", "nb_devoirs_rendus", "retards_rendus"):
        # Comparaison en valeurs : conform type les entiers en Int64, le service en float.
        pd.testing.assert_series_equal(
            service[colonne].astype("float64"),
            attendu[colonne].astype("float64"),
            check_names=False,
        )


def test_conformation_categorielle_egale_preparation():
    raw = _raw()
    attendu = preparation.conform(raw, _profile())
    service = normalization.conform_frame(raw, _facts())
    pd.testing.assert_series_equal(service["filiere"], attendu["filiere"], check_names=False)


def test_derivees_egales_build_gold():
    silver = pd.DataFrame(
        {
            "nb_devoirs_total": [10, 12, 0, 9],  # une ligne à 0 : dénominateur nul -> NaN
            "nb_devoirs_rendus": [8, 12, 0, 9],
            "retards_rendus": [1, 0, 0, 2],
            "autre": [1, 2, 3, 4],
        }
    )
    gold, _ = preparation.build_gold(silver, drop_columns=["autre"])
    service = normalization.add_derived(silver)
    for colonne in ("taux_rendu", "ratio_retards"):
        pd.testing.assert_series_equal(service[colonne], gold[colonne], check_names=False)


def test_colonnes_hors_typage_laissees_intactes():
    raw = _raw()
    raw["reference_dossier"] = ["a1", "b2", "c3", "d4"]  # métadonnée, ni numérique ni catégorielle
    service = normalization.conform_frame(raw, _facts())
    # La référence de dossier traverse sans transformation : son sort revient à la validation.
    pd.testing.assert_series_equal(service["reference_dossier"], raw["reference_dossier"])
