"""Moteur d'export Excel du récapitulatif de contrôle des configurations (§15.4 du notebook).

Ce module ne porte que la *présentation* : un onglet par cible, colonnes groupées
(Train folds / Train OOF / Test scellé), en-têtes fusionnés, formats numériques et statut coloré.
Il reçoit un `DataFrame` déjà constitué et une disposition (`layout`) décrivant, colonne par
colonne, `(groupe | None, en-tête, colonne source, format numérique)`. Aucune décision de
modélisation ne vit ici - la table des configurations et leurs statuts restent au notebook.
"""

import pandas as pd
import xlsxwriter

# Une disposition = liste de colonnes ; chaque colonne est (groupe | None, en-tête, source, format).
Layout = list[tuple[str | None, str, str, str]]

# Palette des bandeaux de groupe (convention de mise en forme, gouvernée par aucun choix métier).
GROUP_BG: dict[str | None, str] = {
    None: "#404040",
    "Train — moy. folds": "#8EA9DB",
    "Train — OOF regroupé": "#B4C6E7",
    "Test scellé": "#F4B183",
}


def classification_layout(seuil_label: str) -> Layout:
    """Disposition de la feuille classification ; `seuil_label` étiquette les colonnes @seuil."""
    return [
        (None, "Modèle", "modèle", "txt"),
        (None, "Hyperparamètres", "hyperparam.", "txt"),
        (None, "Jeu (features)", "jeu", "txt"),
        ("Train — moy. folds", "ROC-AUC", "roc_folds", "auc"),
        ("Train — moy. folds", "PR-AUC", "pr_folds", "auc"),
        ("Train — moy. folds", "Brier", "brier_folds", "brier"),
        ("Train — OOF regroupé", "ROC-AUC", "roc_oof", "auc"),
        ("Train — OOF regroupé", "PR-AUC", "pr_oof", "auc"),
        ("Train — OOF regroupé", "Brier", "brier_oof", "brier"),
        ("Test scellé", "ROC-AUC", "roc_test", "auc"),
        ("Test scellé", "PR-AUC", "pr_test", "auc"),
        ("Test scellé", "Brier", "brier_test", "brier"),
        ("Test scellé", f"Précision @{seuil_label}", "precision_test", "pct"),
        ("Test scellé", f"Rappel @{seuil_label}", "rappel_test", "pct"),
        (None, "Statut", "statut", "txt"),
        (None, "Sections", "sections", "txt"),
    ]


def regression_layout() -> Layout:
    """Disposition de la feuille régression (MAE/RMSE/R² en OOF regroupé et sur le test scellé)."""
    return [
        (None, "Modèle", "modèle", "txt"),
        (None, "Hyperparamètres", "hyperparam.", "txt"),
        (None, "Jeu (features)", "jeu", "txt"),
        ("Train — OOF regroupé", "MAE", "mae_oof", "reg2"),
        ("Train — OOF regroupé", "RMSE", "rmse_oof", "reg2"),
        ("Train — OOF regroupé", "R²", "r2_oof", "r2"),
        ("Test scellé", "MAE", "mae_test", "reg2"),
        ("Test scellé", "RMSE", "rmse_test", "reg2"),
        ("Test scellé", "R²", "r2_test", "r2"),
        (None, "Statut", "statut", "txt"),
        (None, "Sections", "sections", "txt"),
    ]


def write_sheet(
    workbook: xlsxwriter.Workbook, name: str, rows: pd.DataFrame, layout: Layout
) -> None:
    """Écrit une feuille : en-têtes groupés fusionnés, formats numériques, statut coloré."""
    ws = workbook.add_worksheet(name)
    ws.freeze_panes(2, 3)
    grp = {
        g: workbook.add_format(
            {
                "bold": True,
                "bg_color": bg,
                "align": "center",
                "valign": "vcenter",
                "border": 1,
                "font_color": "white" if g is None else "black",
            }
        )
        for g, bg in GROUP_BG.items()
    }
    sub = workbook.add_format(
        {
            "bold": True,
            "bg_color": "#F2F2F2",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "text_wrap": True,
        }
    )
    num = {
        "txt": workbook.add_format({"border": 1, "valign": "vcenter"}),
        "auc": workbook.add_format({"num_format": "0.000", "border": 1, "align": "center"}),
        "brier": workbook.add_format({"num_format": "0.0000", "border": 1, "align": "center"}),
        "pct": workbook.add_format({"num_format": "0.0%", "border": 1, "align": "center"}),
        "reg2": workbook.add_format({"num_format": "0.00", "border": 1, "align": "center"}),
        "r2": workbook.add_format({"num_format": "0.000", "border": 1, "align": "center"}),
    }
    coul = {
        "Validé": workbook.add_format(
            {
                "bg_color": "#C6EFCE",
                "font_color": "#006100",
                "bold": True,
                "border": 1,
                "align": "center",
            }
        ),
        "Écarté": workbook.add_format(
            {
                "bg_color": "#FFC7CE",
                "font_color": "#9C0006",
                "bold": True,
                "border": 1,
                "align": "center",
            }
        ),
        "Comparé": workbook.add_format(
            {"bg_color": "#F2F2F2", "font_color": "#808080", "border": 1, "align": "center"}
        ),
    }
    n = len(layout)
    c = 0
    while c < n:
        g = layout[c][0]
        if g is None:
            ws.merge_range(0, c, 1, c, layout[c][1], grp[None])
            c += 1
        else:
            j = c
            while j < n and layout[j][0] == g:
                j += 1
            ws.merge_range(0, c, 0, j - 1, g, grp[g])
            for k in range(c, j):
                ws.write(1, k, layout[k][1], sub)
            c = j
    for r, (_, row) in enumerate(rows.iterrows(), start=2):
        for cc, (_, _, col, kind) in enumerate(layout):
            val = row.get(col)
            if col == "statut":
                ws.write(r, cc, val, coul.get(val, num["txt"]))
            elif kind == "txt":
                ws.write(r, cc, "" if pd.isna(val) else val, num["txt"])
            elif pd.isna(val):
                ws.write_blank(r, cc, None, num[kind])
            else:
                ws.write_number(r, cc, float(val), num[kind])
    ws.set_column(0, 0, 24)
    ws.set_column(1, 2, 24)
    ws.set_column(3, n - 3, 11)
    ws.set_column(n - 2, n - 2, 10)
    ws.set_column(n - 1, n - 1, 18)


def write_metrics_workbook(path, sheets: list[tuple[str, pd.DataFrame, Layout]]) -> None:
    """Écrit un classeur ; `sheets` = liste de `(nom, DataFrame, layout)`. Encapsule xlsxwriter."""
    workbook = xlsxwriter.Workbook(str(path))
    for name, rows, layout in sheets:
        write_sheet(workbook, name, rows, layout)
    workbook.close()
