"""Conformation d'entrée du service — mêmes primitives que la préparation, sans profil.

Le notebook conforme via un profil recalculé sur les données (`preparation.conform`) ; le
service, lui, ne dispose pas d'un profil : il connaît le typage par la **fiche** et applique
les **mêmes primitives pures** (`cleaning_utils.parse_number` / `normalize_text`). L'identité
des résultats tient donc à la réutilisation de ces primitives — et non à une réécriture — et
est **vérifiée par des tests d'anti-divergence** qui confrontent cette conformation à
`preparation.conform` et `build_gold` sur les mêmes entrées.

Les unités à retirer d'un champ numérique (« % », « km »…) sont **déclarées dans la fiche**
(`ModelFacts.units`), la même information que `detect_units` mesure côté préparation, jamais
devinée ici. Les features **dérivées** (`taux_rendu`, `ratio_retards`) sont calculées par le
même quotient que `build_gold`, l'appelant ne les transmet pas.

Tout est **vectorisé** : un lot de campagne comme un dossier unique passent par le même code,
colonne par colonne.
"""

import pandas as pd

from decrochage_l1.data.utils import cleaning_utils as cleaning
from decrochage_l1.serving.contract import ModelFacts


def conform_frame(raw: pd.DataFrame, facts: ModelFacts) -> pd.DataFrame:
    """Conforme l'**écriture** des colonnes d'entrée selon le typage et les unités de la fiche.

    Numérique : cellules vides ramenées à un manquant, puis `parse_number` avec les unités
    déclarées (virgule décimale et suffixe collé gérés). Catégoriel : `normalize_text`
    (minuscules, sans accent, espaces normalisés). Les autres colonnes — référence de dossier,
    champs hors périmètre — sont laissées telles quelles ; leur sort revient à la validation.

    Aucune valeur n'est jugée ici : une écriture change, jamais une information.
    """
    numeric = set(facts.numeric)
    categorical = set(facts.categorical)
    out = raw.copy()
    for column in raw.columns:
        if column in numeric:
            values = cleaning.blank_to_na(out[column])
            out[column] = cleaning.parse_number(values, facts.units.get(column, ()))
        elif column in categorical:
            out[column] = cleaning.normalize_text(out[column])
    return out


def add_derived(frame: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les features dérivées ligne à ligne — même quotient que `preparation.build_gold`.

    `taux_rendu` et `ratio_retards` sont rapportés au **nombre de devoirs attendus**
    (`nb_devoirs_total`), dénominateur commun qui les rend comparables d'un étudiant à l'autre.
    Division sûre : `NaN` là où le dénominateur manque ou vaut 0, jamais un `inf`.

    Ce quotient est **dupliqué** de `build_gold` (le service ne repart pas des paliers) : un
    test d'anti-divergence garantit qu'ils restent identiques, et casserait si l'un changeait.
    Chaque dérivée n'est ajoutée que si ses colonnes source sont présentes — un contrat qui
    n'en déclare qu'une, ou un lot partiel, ne fait pas échouer la conformation.
    """
    out = frame.copy()
    if "nb_devoirs_total" not in out:
        return out
    denominator = out["nb_devoirs_total"].where(out["nb_devoirs_total"] > 0)
    if "nb_devoirs_rendus" in out:
        out["taux_rendu"] = out["nb_devoirs_rendus"] / denominator
    if "retards_rendus" in out:
        out["ratio_retards"] = out["retards_rendus"] / denominator
    return out
