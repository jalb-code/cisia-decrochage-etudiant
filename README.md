# decrochage-l1

Détection précoce des étudiants en risque de décrochage en L1.
Cas d'usage de certification IA « Concevoir et implémenter une solution d'intelligence
artificielle » (référentiel C1 → C9).

## Problème

Un seul dataset observé **à mi-parcours du S1**, deux cibles apprises en parallèle :

- **`abandon`** (0/1) — classification binaire (cible principale) ;
- **`moyenne_finale`** (/20) — régression (cible secondaire).

## Trois manières de faire tourner le projet

Le dépôt expose la même chaîne de traitement sous **trois surfaces**, chacune autonome :

| Solution | Ce qu'elle fait | Dépendances | Fichiers de conf |
|---|---|---|---|
| **Notebook** | le livrable certifiant : produit et défend toute la démarche (§0 → §15) | `--group analysis` | [`.env`](.env.exemple) |
| **CLI** | rejoue la chaîne pour **prédire** ou **ré-entraîner** en ligne de commande | `--group cli` | [`configs/pipeline_spec.json`](configs/pipeline_spec.json), [`.env`](.env.exemple) |
| **Service d'inférence** | expose le modèle en **API** + **supervision** + **client de démo** (Docker) | image runtime | [`deploy/docker-compose.yml`](deploy/docker-compose.yml), [`deploy/monitoring/`](deploy/monitoring/), [`.env`](.env.exemple) |

Toute la configuration d'exécution passe par un fichier **`.env`** (copié depuis
[`.env.exemple`](.env.exemple), qui liste **toutes** les variables possibles) : c'est lui que lisent
[`config.py`](src/decrochage_l1/config.py) (chemins, préfixe `DECROCHAGE_L1_`) et
[`serving/settings.py`](src/decrochage_l1/serving/settings.py) (service, préfixe `DECROCHAGE_`) —
on n'édite pas le code pour régler le projet.

Un préalable commun (environnement `uv`, dépôt des données) précède les trois.

## Préalable commun

Projet géré avec [uv](https://docs.astral.sh/uv/) — la version de Python et les dépendances sont
définies dans [`pyproject.toml`](pyproject.toml). Les dépendances sont **séparées par usage** : le
groupe par défaut est le *runtime strict du service d'inférence* (l'empreinte de l'image Docker) ;
chaque solution ci-dessous précise le groupe à installer en plus.

### Déposer les données (obligatoire pour le notebook et le ré-entraînement)

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
par le code**, jamais déposés à la main. Détail : [data/README.md](data/README.md). Pour viser un
autre jeu de dossiers, poser `DECROCHAGE_L1_ROOT_DIR` dans [`.env`](.env.exemple) (voir ce fichier).

---

## Solution 1 — Notebook (livrable certifiant)

Le livrable de la certification : un notebook unique qui **produit et défend** toute la démarche
(EDA, préparation, choix du modèle, entraînement, explicabilité, industrialisation), en 16 sections
lisibles sans explication orale.

**Fichier de conf** — [`.env`](.env.exemple) pour les chemins (`DECROCHAGE_L1_ROOT_DIR`). La stack
est figée dans [`pyproject.toml`](pyproject.toml) (installée par `uv sync`, non éditée pour régler) ;
les jeux relèvent du préalable commun ci-dessus.

```bash
uv sync --group analysis      # runtime + outillage d'étude (SHAP, XGBoost, Optuna, matplotlib, CodeCarbon)
uv run pre-commit install
```

Ouvrir [`notebooks/JALB-Decrochage-l1.ipynb`](notebooks/JALB-Decrochage-l1.ipynb) avec le `.venv`
créé par `uv sync --group analysis` comme noyau (Jupyter ou VS Code), puis exécuter dans l'ordre.

Vérifier le code et lancer la suite de tests complète (le notebook et le modeling §8-§9-§12 exigent
le groupe `analysis`) :

```bash
uv run ruff check .           # lint
uv run ruff format .          # formatage
uv run pytest                 # suite complète (nécessite --group analysis)
```

---

## Solution 2 — CLI (prédire et ré-entraîner)

La commande `decrochage-l1` rejoue la chaîne en ligne de commande, sans interface graphique. Elle
relit les jugements éprouvés figés dans [`configs/pipeline_spec.json`](configs/pipeline_spec.json)
(exclusions, features, seed, hyperparamètres, seuil) et **n'optimise jamais les hyperparamètres**
(gelés dans la spec).

**Fichiers de conf** — [`configs/pipeline_spec.json`](configs/pipeline_spec.json) (jugements figés)
et [`.env`](.env.exemple) pour les chemins d'entrée/sortie (`DECROCHAGE_L1_ROOT_DIR`).

```bash
uv sync --group cli           # installe typer (hors image d'inférence)
uv run decrochage-l1 --help
```

**Prédire** — scorer un CSV de dossiers reçus (écritures libres tolérées : « 67,2 % », virgules,
accents, modalités hors vocabulaire). Un dossier soumis = une ligne scorée, référence préservée :

```bash
# jeu d'exemple fourni (20 dossiers avec erreurs de saisie, sans cible)
uv run decrochage-l1 predict \
  --input docs/exemple/cohorte_20_avec_erreurs.csv \
  --output reports/scores.csv
# --indicator expose en plus l'indicateur binaire (seuil de la fiche) ; par défaut, probabilité seule (art. 22)
```

**Ré-entraîner** — repartir d'un nouveau jeu **étiqueté** (mêmes colonnes que le jeu d'origine) et
rejouer bronze → silver → gold → entraînement → package, à **iso-périmètre** :

```bash
uv run decrochage-l1 retrain \
  --students "data/raw/dataset decrochage_etudiants_complet_V5.csv"
# --spec <fichier>     : spec figée à relire (défaut : configs/pipeline_spec.json)
# --artifacts <dir>    : dossier de sortie de l'artefact (défaut : artifacts/)
# --no-save-paliers    : ne pas écrire bronze/silver/gold sous data/ (l'artefact est produit quand même)
```

> Le jeu d'exemple `cohorte_20_avec_erreurs.csv` est un jeu de **`predict`** (pas de cibles, 20 lignes) :
> le ré-entraînement exige des **labels** et assez de lignes pour le split et la validation croisée.

---

## Solution 3 — Service d'inférence (API + supervision + client de démo)

Sert le modèle figé (§10) derrière une **API FastAPI** — runtime pur, sans outillage d'analyse :
`POST /v1/predict-cohorte`, `POST /v1/predict-etudiant`, `GET /v1/modele`, `GET /v1/seuil`,
`/health`, `/ready`, `/metrics`. La logique vit dans
[`src/decrochage_l1/serving/`](src/decrochage_l1/serving/) (contrat/fiche, entrepôt, normalisation,
validation, explicabilité, dérive, métriques Prometheus).

**Fichiers de conf** :

- [`deploy/docker-compose.yml`](deploy/docker-compose.yml) — les 4 services (api, prometheus, grafana, client) ;
- [`deploy/Dockerfile`](deploy/Dockerfile) — image d'inférence (runtime seul, absence des libs d'analyse vérifiée au build) ;
- [`deploy/monitoring/`](deploy/monitoring/) — collecteur Prometheus (`prometheus.yml`, `regles.yml`)
  et tableau de bord Grafana (provisioning + `dashboards/decrochage.json`) ;
- `artifacts/` — les artefacts §10/§12, montés en **lecture seule** ; absents, `/ready` répond 503
  sans empêcher le démarrage ;
- [`.env`](.env.exemple) — variables d'exploitation ; copier depuis [`.env.exemple`](.env.exemple)
  et renseigner au moins `DECROCHAGE_API_KEYS` (sans clé, les routes protégées répondent 503).

Préparer l'environnement une fois :

```bash
cp .env.exemple .env          # puis renseigner DECROCHAGE_API_KEYS
```

Chaque commande ne démarre **que les conteneurs nommés** (compose ne tire que leurs dépendances,
jamais l'inverse).

**Lancement Service d'inférence** — démarre **3 conteneurs** (`api`, `prometheus`, `grafana`) :
l'API et sa supervision, sans le client :

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build api prometheus grafana
```

**Lancement Client de démonstration** *(prérequis : service d'inférence déjà `up`)* — ajoute le
conteneur `client` à la pile en cours :

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build client
```

**Lancement complet** — les **4 conteneurs** d'un coup (aucun service nommé = toute la pile) :

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

| Surface | URL | Lancement |
|---|---|---|
| API — documentation Swagger | http://localhost:8000/docs | Service d'inférence |
| Prometheus | http://localhost:9090 | Service d'inférence |
| Grafana — supervision | http://localhost:3000 | Service d'inférence |
| Client de démonstration | http://localhost:8080 | Client de démonstration |

Le **client** (`client/`) est **hors périmètre livré** : c'est une simple maquette statique qui sert
la démonstration (clé d'API saisie côté navigateur, usage localhost), pas un composant du produit.

Pour lancer l'API seule **sans Docker** (runtime `uv sync`, sans conteneur) :

```bash
DECROCHAGE_API_KEYS=ma-cle uv run uvicorn decrochage_l1.serving.api:app --port 8000
```

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
  cli.py              CLI `decrochage-l1` : predict / retrain hors notebook (§13)
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
artifacts/   livrables produits par le code : 2 pipelines + fiche (joblib, §10), contrat I/O
             JSON, model card + métadonnées (§12). Joblib hors dépôt ; documents versionnables
reports/     rapports de profilage HTML (générés, hors dépôt : ils citent des valeurs brutes)
notebooks/   LE notebook certifiant unique (JALB-Decrochage-l1.ipynb)
configs/     jugements éprouvés figés (pipeline_spec.json) relus par la CLI (§13)
deploy/      Dockerfile (image runtime seul), docker-compose, monitoring Prometheus/Grafana
client/      maquette de présentation (statique, hors périmètre livré)
docs/
  exemple/                jeux d'exemple pour la CLI (cohortes avec / sans erreurs de saisie)
  registre-decisions.csv  registre des questions et décisions (vue de navigation)
  cas_usage/              énoncé du cas d'usage
  support_formation/      supports de formation (local, non versionné)  
```

Contexte de travail, démarche et consignes détaillées : voir [CLAUDE.md](CLAUDE.md).
