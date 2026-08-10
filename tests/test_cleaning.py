"""Tests des primitives de mise en forme.

Chaque cas reproduit une écriture réellement présente dans les fichiers du cas
d'usage — nombre stocké en texte, unité collée, virgule décimale, date en
plusieurs formats, casse et espaces hétérogènes.

Les formats de date sont passés en littéraux : ces tests portent sur le
comportement de la primitive, pas sur le contrat des fichiers du projet.
"""

import pandas as pd
import pytest

from decrochage_l1.data import cleaning

FORMATS_DATE = ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y")


@pytest.mark.parametrize("blanc", ["", "   ", "\t"])
def test_blank_to_na_treats_any_blank_as_missing(blanc):
    """Un blanc est une absence, quelle que soit son écriture — jamais une modalité."""
    result = cleaning.blank_to_na(pd.Series(["Informatique", blanc, None]))
    assert result[0] == "Informatique"
    assert result[1:].isna().all()


def test_normalize_text_removes_accents_case_and_spaces():
    values = pd.Series([" Général ", "GENERAL", "général", None])
    result = cleaning.normalize_text(values)
    assert list(result[:3]) == ["general"] * 3
    assert pd.isna(result[3])


def test_normalize_text_collapses_inner_spaces():
    """Deux espaces internes ou un seul désignent la même modalité."""
    result = cleaning.normalize_text(pd.Series(["Lettres  Modernes", "lettres modernes"]))
    assert result[0] == result[1] == "lettres modernes"


@pytest.mark.parametrize(
    ("raw", "units", "expected"),
    [
        ("18.8", (), 18.8),  # point décimal
        ("2,2", (), 2.2),  # virgule décimale
        ("12.0 km", ("km",), 12.0),  # unité collée
        ("77.5%", ("%",), 77.5),  # symbole pourcentage
        ("86,3", ("%",), 86.3),  # virgule sans symbole
        ("n/a", (), None),  # inconvertible -> NaN, pas d'exception
    ],
)
def test_parse_number_covers_the_notations_of_the_source(raw, units, expected):
    result = cleaning.parse_number(pd.Series([raw]), units)[0]
    if expected is None:
        assert pd.isna(result)
    else:
        assert result == pytest.approx(expected)


def test_parse_date_recognizes_the_three_formats():
    values = pd.Series(["04 Sep 2024", "2024-09-27", "26/09/2024", None, "pas une date"])
    result = cleaning.parse_date(values, FORMATS_DATE)
    assert list(result[:3]) == [
        pd.Timestamp("2024-09-04"),
        pd.Timestamp("2024-09-27"),
        pd.Timestamp("2024-09-26"),
    ]
    assert result[3:].isna().all()


def test_parse_date_does_not_confuse_day_and_month():
    """« 04/09/2024 » est le 4 septembre, pas le 9 avril : format explicite, pas deviné."""
    result = cleaning.parse_date(pd.Series(["04/09/2024"]), FORMATS_DATE)
    assert result[0] == pd.Timestamp("2024-09-04")


def test_primitives_give_the_same_result_on_one_row_as_on_a_batch():
    """Aucune primitive n'apprend quoi que ce soit du lot : une ligne suffit."""
    lot = pd.Series(["12.0 km", "2,2", "18.8"])
    for position, valeur in enumerate(lot):
        seule = cleaning.parse_number(pd.Series([valeur]), ("km",))[0]
        assert seule == pytest.approx(cleaning.parse_number(lot, ("km",))[position])
