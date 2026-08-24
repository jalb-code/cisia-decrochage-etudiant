"""Construit le livrable (dossier `dist/` + archive `.zip`) depuis les sources validées du dépôt.

Deux garanties, sinon le script s'arrête sans rien produire :

1. **Sorties présentes** - le notebook packagé doit être *exécuté* (aucune cellule de code non
   vide sans `execution_count`). L'énoncé exige un notebook intégrant « texte, code, résultats » :
   on refuse de livrer un notebook vierge de sorties. Exécuter « Run All » avant de construire.
2. **Zéro erreur de lint** - `ruff check` doit passer sur le notebook packagé. Le livrable est
   ainsi une *sortie* de contrôle, jamais une copie éditée à la main après le pre-commit.

Le livrable embarque le jeu de référence `data/gold/`, les artefacts sérialisés `artifacts/` et les
rapports de profilage `reports/*.html`, pour que le §4 « jeu de données préparé » soit satisfait et
que les liens du notebook exécuté (§15.2) résolvent dans l'archive.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVRABLE_NOM = "Alburquerque_Julien_decrochage-l1"
NOTEBOOK_REL = "notebooks/JALB-Decrochage-l1.ipynb"

# Ordures à ne jamais recopier dans un dossier du livrable (.gitkeep n'a de sens que dans Git,
# où il préserve un dossier vide : dans le livrable, les dossiers portent de vrais fichiers).
IGNORER = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".ruff_cache", "*.bak", "history", ".gitkeep", ".gitignore"
)

# Fichiers copiés tels quels : (source relative au dépôt, destination relative au livrable).
FICHIERS = [
    (
        "notebooks/JALB-JournalDeBord-Decrochage-l1.ipynb",
        "notebooks/JALB-JournalDeBord-Decrochage-l1.ipynb",
    ),
    ("docs/JALB-Decrochage-l1.pptx", "JALB-Decrochage-l1.pptx"),
    ("docs/registre-decisions.csv", "docs/registre-decisions.csv"),
    ("LISEZ-MOI.md", "LISEZ-MOI.md"),
    ("README.md", "README.md"),
    ("pyproject.toml", "pyproject.toml"),
    ("uv.lock", "uv.lock"),
    (".python-version", ".python-version"),
    ("configs/pipeline_spec.json", "configs/pipeline_spec.json"),
    ("data/README.md", "data/README.md"),
]

# Dossiers copiés récursivement (hors ordures). Gold, artefacts et raw satisfont §4/§5.
DOSSIERS = [
    ("notebooks/ressources", "notebooks/ressources"),
    ("src/decrochage_l1", "src/decrochage_l1"),
    ("data/raw", "data/raw"),
    ("data/sample", "data/sample"),
    ("data/gold", "data/gold"),
    ("artifacts", "artifacts"),
]


def verifier_notebook_execute(notebook: Path) -> None:
    """Arrête le script si une cellule de code non vide n'a pas de sortie d'exécution."""
    nb = json.loads(notebook.read_text(encoding="utf-8"))
    non_executees = [
        i
        for i, cell in enumerate(nb["cells"])
        if cell["cell_type"] == "code"
        and "".join(cell.get("source", [])).strip()
        and cell.get("execution_count") is None
    ]
    if non_executees:
        sys.exit(
            f"ÉCHEC (sorties absentes) : {len(non_executees)} cellule(s) de code sans sortie "
            f"(execution_count=None), aux index {non_executees}. "
            "Exécuter « Run All » sur le notebook avant de construire le livrable."
        )


def verifier_lint(notebook: Path) -> None:
    """Arrête le script si `ruff check` signale une erreur sur le notebook packagé."""
    resultat = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(notebook)],
        capture_output=True,
        text=True,
    )
    if resultat.returncode != 0:
        sys.exit(f"ÉCHEC (lint) : ruff signale une erreur dans le notebook :\n{resultat.stdout}")


def copier(out_dir: Path, notebook: Path) -> None:
    """Vide le dossier de sortie puis y recopie le manifeste (fichiers, dossiers, rapports HTML)."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    (out_dir / "notebooks").mkdir(parents=True, exist_ok=True)
    shutil.copy2(notebook, out_dir / NOTEBOOK_REL)

    for source, dest in FICHIERS:
        cible = out_dir / dest
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, cible)

    for source, dest in DOSSIERS:
        shutil.copytree(ROOT / source, out_dir / dest, ignore=IGNORER)

    rapports = sorted((ROOT / "reports").glob("profil-*.html"))
    if not rapports:
        sys.exit("ÉCHEC : aucun rapport de profilage `reports/profil-*.html` à livrer.")
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    for html in rapports:
        shutil.copy2(html, out_dir / "reports" / html.name)

    nettoyer(out_dir)


def nettoyer(out_dir: Path) -> None:
    """Filet de sécurité : purge tout cache ou marqueur Git qui aurait pu apparaître dans la sortie.

    Un `ruff`/`pytest` lancé par mégarde depuis le livrable y dépose un `.ruff_cache` :
    on le retire ici pour que dossier et archive restent propres quoi qu'il arrive.
    """
    for chemin in sorted(out_dir.rglob("*"), reverse=True):
        if chemin.is_dir() and chemin.name in {".ruff_cache", "__pycache__"}:
            shutil.rmtree(chemin, ignore_errors=True)
        elif chemin.is_file() and (
            chemin.name in {".gitkeep", ".gitignore"} or chemin.suffix in {".pyc", ".bak"}
        ):
            chemin.unlink(missing_ok=True)


def zipper(out_dir: Path) -> Path:
    """Archive le dossier du livrable, préfixé par son nom, en `<nom>.zip`."""
    archive = out_dir.parent / f"{LIVRABLE_NOM}.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for chemin in sorted(out_dir.rglob("*")):
            if chemin.is_file():
                zf.write(chemin, Path(LIVRABLE_NOM) / chemin.relative_to(out_dir))
    return archive


def main() -> None:
    """Point d'entrée : contrôle le notebook, assemble le livrable, produit l'archive."""
    parser = argparse.ArgumentParser(description="Construit le livrable de certification.")
    parser.add_argument(
        "--notebook",
        type=Path,
        default=ROOT / NOTEBOOK_REL,
        help="Notebook exécuté à packager (défaut : la version du dépôt).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "dist" / LIVRABLE_NOM,
        help="Dossier de sortie du livrable (défaut : dist/<nom>).",
    )
    parser.add_argument("--no-zip", action="store_true", help="Ne pas produire l'archive .zip.")
    args = parser.parse_args()

    verifier_notebook_execute(args.notebook)
    verifier_lint(args.notebook)
    copier(args.out, args.notebook)
    nb_fichiers = sum(1 for p in args.out.rglob("*") if p.is_file())
    print(f"Livrable assemblé : {args.out} ({nb_fichiers} fichiers).")
    if not args.no_zip:
        archive = zipper(args.out)
        print(f"Archive : {archive} ({archive.stat().st_size // 1024} Kio).")


if __name__ == "__main__":
    main()
