"""Features dérivées du service — mêmes quotients que la préparation, calculés côté serveur.

L'entrée du service est **typée et validée** par le schéma Pydantic
(`schemas.PredictEtudiantForm`) : les colonnes arrivent déjà propres (nombres, modalités
canoniques), le service n'a donc plus à conformer l'écriture. Il reste à calculer les features
**dérivées** (`taux_rendu`, `ratio_retards`), que l'appelant ne transmet pas — par le même
quotient que `preparation.build_gold`.

Tout est **vectorisé** : un lot de campagne comme un dossier unique passent par le même code.
"""

import pandas as pd


def add_derived(frame: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les features dérivées ligne à ligne — même quotient que `preparation.build_gold`.

    `taux_rendu` et `ratio_retards` sont rapportés au **nombre de devoirs attendus**
    (`nb_devoirs_total`), dénominateur commun qui les rend comparables d'un étudiant à l'autre.
    Division sûre : `NaN` là où le dénominateur manque ou vaut 0, jamais un `inf`.

    Ce quotient est **dupliqué** de `build_gold` (le service ne repart pas des paliers) : un
    test d'anti-divergence garantit qu'ils restent identiques, et casserait si l'un changeait.
    Chaque dérivée n'est ajoutée que si ses colonnes source sont présentes.
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
