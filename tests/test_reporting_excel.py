"""Tests du moteur d'export Excel (§15.4).

On vérifie deux choses distinctes : les dispositions (fonctions pures - structure des groupes,
étiquette de seuil injectée dans les en-têtes) et l'écriture d'un classeur réel (fichier .xlsx
valide, présence des deux onglets), sans dépendre d'un lecteur Excel (openpyxl absent) : un .xlsx
est un zip, on y lit les noms d'onglets dans `xl/workbook.xml`.
"""

import zipfile

import pandas as pd

from decrochage_l1.reporting import excel


def test_classification_layout_injecte_le_seuil():
    """L'étiquette de seuil se retrouve dans les en-têtes précision/rappel."""
    layout = excel.classification_layout("0,42")
    headers = [entry[1] for entry in layout]
    assert "Précision @0,42" in headers
    assert "Rappel @0,42" in headers
    # Toute colonne source doit avoir un format connu du moteur d'écriture.
    formats = {"txt", "auc", "brier", "pct", "reg2", "r2"}
    assert all(entry[3] in formats for entry in layout)


def test_regression_layout_structure():
    """La feuille régression ne porte que MAE/RMSE/R², en OOF puis test scellé."""
    layout = excel.regression_layout()
    groupes = {entry[0] for entry in layout}
    assert "Train — OOF regroupé" in groupes
    assert "Test scellé" in groupes
    sources = [entry[2] for entry in layout]
    assert sources.count("mae_oof") == 1
    assert sources.count("mae_test") == 1


def test_group_bg_couvre_les_groupes_du_layout():
    """Chaque groupe d'une disposition a une couleur de bandeau déclarée (sinon KeyError)."""
    for layout in (excel.classification_layout("0,42"), excel.regression_layout()):
        for groupe, *_ in layout:
            assert groupe in excel.GROUP_BG


def _mini_frame():
    """Deux lignes minimales couvrant statut coloré, valeur numérique et cellule vide."""
    return pd.DataFrame(
        [
            {
                "modèle": "Logreg",
                "hyperparam.": "défaut",
                "jeu": "minimisé (16)",
                "roc_oof": 0.945,
                "pr_oof": 0.872,
                "brier_oof": 0.08,
                "roc_folds": 0.94,
                "pr_folds": 0.87,
                "brier_folds": 0.08,
                "roc_test": 0.945,
                "pr_test": 0.872,
                "brier_test": 0.08,
                "precision_test": 0.77,
                "rappel_test": 0.79,
                "statut": "Validé",
                "sections": "§9",
            },
            {
                "modèle": "RF",
                "hyperparam.": "défaut",
                "jeu": "complet (24)",
                "roc_oof": 0.93,
                "pr_oof": 0.85,
                "brier_oof": 0.09,
                "roc_folds": 0.93,
                "pr_folds": 0.85,
                "brier_folds": 0.09,
                "roc_test": None,
                "pr_test": None,
                "brier_test": None,
                "precision_test": None,
                "rappel_test": None,
                "statut": "Comparé",
                "sections": "§8",
            },
        ]
    )


def test_write_metrics_workbook_produit_un_xlsx_valide(tmp_path):
    """Le classeur écrit est un .xlsx valide portant les deux onglets demandés."""
    chemin = tmp_path / "metrics.xlsx"
    frame = _mini_frame()
    excel.write_metrics_workbook(
        chemin,
        [
            ("abandon", frame, excel.classification_layout("0,42")),
            ("moyenne_finale", frame, excel.regression_layout()),
        ],
    )
    assert chemin.exists() and chemin.stat().st_size > 0
    with zipfile.ZipFile(chemin) as zf:
        workbook_xml = zf.read("xl/workbook.xml").decode("utf-8")
    assert 'name="abandon"' in workbook_xml
    assert 'name="moyenne_finale"' in workbook_xml
