"""Test d'ANTI-DIVERGENCE des features dérivées : le service doit égaler `build_gold`.

Le service calcule `taux_rendu`/`ratio_retards` par le même quotient que la préparation ;
ce test casserait si l'un des deux côtés changeait sans l'autre — c'est sa raison d'être.
"""

import pandas as pd

from decrochage_l1.data import preparation
from decrochage_l1.serving import normalization


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
