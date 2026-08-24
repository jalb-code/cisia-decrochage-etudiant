"""Garde anti-régression SSOT/DRY.

Interdit qu'un fichier **versionné** cite un *fichier* de `docs/local/` (zone de travail non
versionnée, non-autoritative). Nommer une **zone** reste autorisé — `docs/local/` comme
`docs/local/reserve/` — seul le renvoi vers un fichier précis est bloqué.

**La distinction est le slash final** : un chemin qui se termine par `/` désigne un dossier, tout
autre chemin désigne un fichier. D'où la convention à tenir dans les fichiers versionnés : écrire
les dossiers avec leur slash.

Motivation : `docs/local/` est une réserve **non-autoritative** — matière à challenger, jamais
source à citer. Un artefact pérenne ne dépend jamais d'un éphémère.

Utilisé comme hook pre-commit : reçoit les fichiers à vérifier en arguments et échoue (code 1)
si une référence fautive est trouvée.
"""

import contextlib
import io
import re
import sys

# Le chemin le plus long possible sous `docs/local/`. Les espaces sont exclus des caractères de
# chemin : sans cela, le motif dévorerait la prose qui suit la citation.
PATTERN = re.compile(r"docs/local/[A-Za-z0-9_.\-/]*")


def check_refs(files: list[str]) -> int:
    """Retourne 1 si un fichier cite un fichier de `docs/local/`, 0 sinon (avec détail imprimé)."""
    errors = 0
    for path in files:
        try:
            with open(path, encoding="utf-8") as stream:
                lines = stream.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue  # binaire ou illisible : ignoré
        for number, line in enumerate(lines, start=1):
            for match in PATTERN.finditer(line):
                if match.group().endswith("/"):
                    continue  # dossier nommé, pas un fichier cité
                print(
                    f"ERREUR {path}:{number} : cite `{match.group()}` "
                    "(zone non-autoritative : interdit)"
                )
                print(f"   {line.strip()}")
                errors += 1
    if errors:
        print(
            f"\n{errors} référence(s) fautive(s) : renvoyer plutôt vers les données "
            "ou vers le notebook, qui portent les faits et les décisions."
        )
    return 1 if errors else 0


if __name__ == "__main__":
    # Sortie robuste quel que soit l'encodage du terminal (Windows cp1252, etc.).
    with contextlib.suppress(ValueError):
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(check_refs(sys.argv[1:]))
