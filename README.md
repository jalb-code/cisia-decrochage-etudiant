# decrochage-l1

Détection précoce des étudiants en risque de décrochage en L1.
Cas d'usage de certification IA « Concevoir et implémenter une solution d'intelligence
artificielle » (référentiel C1 → C9).

## Problème

Un seul dataset observé **à mi-parcours du S1**, deux cibles apprises en parallèle :

- **`abandon`** (0/1) — classification binaire (cible principale) ;
- **`moyenne_finale`** (/20) — régression (cible secondaire).

## Démarrage

Projet géré avec [uv](https://docs.astral.sh/uv/) — la version de Python et les dépendances sont
définies dans [`pyproject.toml`](pyproject.toml) et installées par `uv sync`.

### 1. Installer l'environnement

```bash
uv sync                 # crée le .venv et installe runtime + dépendances de dev
uv run pre-commit install
```

### 2. Déposer les données (obligatoire)

Les jeux de données **ne sont pas versionnés** : un fichier entré dans l'historique Git y demeure,
et il s'agit de données scolaires nominatives. Le dépôt cloné **ne s'exécute donc pas tel quel** :
il faut d'abord approvisionner `data/` à la main, en respectant **exactement** les noms de fichiers
(espaces inclus) :

```
data/raw/dataset decrochage_etudiants_complet_V5.csv
data/raw/dataset catalogue_formations_V5.csv
data/sample/dataset decrochage_etudiants_echantillon_V5.csv
```

Les dossiers `bronze/`, `silver/` et `gold/` restent vides : les trois **paliers** sont **produits
par le code**, jamais déposés à la main. Détail : [data/README.md](data/README.md).

### 3. Vérifier, tester, exécuter

```bash
uv run ruff check .     # lint
uv run ruff format .    # formatage
uv run pytest           # tests unitaires
```

Le notebook `notebooks/JALB-Decrochage-l1.ipynb` s'ouvre avec le `.venv` créé par `uv sync`
comme noyau (Jupyter / VS Code).

## Arborescence

```
data/            zone de dépôt (raw, sample) puis paliers produits par le code
  raw/       jeux de données bruts fournis (5 240 lignes / 5 200 étudiants, + catalogue formations)
  sample/    échantillon de 50 lignes (première lecture)
  bronze/    copie exacte des fichiers reçus, immuable
  silver/    écritures conformées, vocabulaire recodé, doublons exacts retirés
  gold/      jeu de référence : propre, annoté, validé, lisible par un humain
src/decrochage_l1/  code source réutilisable, importable et testé
  config.py           réglages d'exécution (chemins), surchargeables par `DECROCHAGE_L1_*`
  eda.py              mesures d'exploration (associations, manquants, extrêmes) + tracés minces
  data/
    preparation.py       mise en forme du cas d'usage : vocabulaire cible + conformation,
                         recodage, dédoublonnage (`transform`). Sert au jeu de travail (§5)
                         puis au palier silver (§7)
    utils/               briques agnostiques du cas d'usage
      profiling_utils.py   profilage d'un CSV : encodage, types, écritures, non-conformité
      profiling_report.py  restitution HTML du profil (mise en page seule)
      cleaning_utils.py    primitives de mise en forme (parsing, normalisation d'écriture)
      recoding_utils.py    mécanisme de recodage (reçoit son vocabulaire, n'en fige aucun)
scripts/     scripts utilitaires (gardes de cohérence du dépôt)
tests/       tests unitaires (pytest, src/ sur le pythonpath)
models/      pipelines sérialisés (joblib)
reports/     rapports de profilage HTML (générés, hors dépôt : ils citent des valeurs brutes)
notebooks/   LE notebook certifiant unique (JALB-Decrochage-l1.ipynb)
docs/
  registre-decisions.csv  registre des questions et décisions (vue de navigation)
  cas_usage/              énoncé du cas d'usage
  support_formation/      supports de formation (local, non versionné)
  local/                  zone de travail non versionnée, NON-AUTORITATIVE
```

Contexte de travail, démarche et consignes détaillées : voir [CLAUDE.md](CLAUDE.md).
