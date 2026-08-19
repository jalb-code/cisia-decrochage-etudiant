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
uv sync                     # runtime du service d'inférence + dépendances de dev
uv sync --group analysis    # + outillage d'étude (SHAP, XGBoost, Optuna, matplotlib, CodeCarbon)
uv run pre-commit install
```

Les dépendances sont **séparées par usage** : le groupe par défaut est le *runtime strict du service
d'inférence* — c'est l'empreinte de l'image Docker ; le groupe **`analysis`** porte l'outillage qui
ne sert qu'à produire le dossier d'étude. **Pour le notebook, le modeling (§8-§9-§12) et la suite de
tests complète, installer aussi `--group analysis`.**

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
uv run pytest           # tests unitaires (suite complète : nécessite --group analysis)
```

Les tests de la couche service (`tests/test_serving_*.py`, `test_api.py`, `test_metrics.py`)
tournent avec le seul runtime ; la suite **complète** (dont `test_modeling.py`, qui importe XGBoost)
exige le groupe `analysis`.

Le notebook `notebooks/JALB-Decrochage-l1.ipynb` s'ouvre avec le `.venv` créé par
`uv sync --group analysis` comme noyau (Jupyter / VS Code).

## Service d'inférence et déploiement (§10 → §13)

La logique de service vit dans [`src/decrochage_l1/serving/`](src/decrochage_l1/serving/) — runtime
pur, sans outillage d'analyse :

- **contrat & artefact** — `contract.py` (fiche du modèle : variables, exclusions motivées, bornes,
  seuils, distribution de référence), `store.py` (`save_bundle` sérialise les deux pipelines + la
  fiche, avec garde-fou anti-fuite) ;
- **traitement** — `normalization.py` (conformation alignée sur la préparation, testée
  anti-divergence), `validation.py` (contrôles ligne à ligne), `explain.py` (contributions
  analytiques du modèle linéaire), `drift.py` (dérive par campagne, PSI/KS) ;
- **API** — `api.py` (FastAPI) : `POST /v1/predict-cohorte`, `POST /v1/predict-etudiant`,
  `GET /v1/modele`, `GET /v1/seuil`, `/health`, `/ready`, `/metrics` ; `metrics.py` (métriques
  métier Prometheus).

Lancer le service seul :

```bash
DECROCHAGE_API_KEYS=ma-cle uv run uvicorn decrochage_l1.serving.api:app --port 8000
```

Pile complète (service + Prometheus + Grafana + maquette de démonstration) :

```bash
cp .env.exemple .env          # renseigner DECROCHAGE_API_KEYS
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

| Surface | URL |
|---|---|
| API — documentation Swagger | http://localhost:8000/docs |
| Maquette de démonstration | http://localhost:8080 |
| Grafana — supervision | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

L'**image d'inférence** n'embarque que le runtime (`uv sync --no-default-groups --no-dev`) ; l'absence
des libs d'analyse y est vérifiée au build. Le modèle (`models/`) est monté en lecture seule — absent,
`/ready` répond 503 sans empêcher le démarrage. La **maquette** (`client/`) est **hors périmètre
livré** : elle sert la démonstration. Variables d'exploitation : [.env.exemple](.env.exemple).

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
  modeling/           préprocesseur appris, familles de modèles, protocole, réglage (§8-§9)
  serving/            service d'inférence (§10-§13), runtime pur : contrat/fiche, entrepôt,
                      normalisation, validation, explicabilité, dérive, API FastAPI, métriques
scripts/     scripts utilitaires (gardes de cohérence du dépôt)
tests/       tests unitaires (pytest, src/ sur le pythonpath)
models/      artefacts sérialisés (joblib) : 2 pipelines + fiche du modèle (§10, hors dépôt)
reports/     rapports de profilage HTML (générés, hors dépôt : ils citent des valeurs brutes)
notebooks/   LE notebook certifiant unique (JALB-Decrochage-l1.ipynb)
deploy/      Dockerfile (image socle-seul), docker-compose, monitoring Prometheus/Grafana
client/      maquette de présentation (statique, hors périmètre livré)
docs/
  registre-decisions.csv  registre des questions et décisions (vue de navigation)
  cas_usage/              énoncé du cas d'usage
  support_formation/      supports de formation (local, non versionné)
  local/                  zone de travail non versionnée, NON-AUTORITATIVE
```

Contexte de travail, démarche et consignes détaillées : voir [CLAUDE.md](CLAUDE.md).
