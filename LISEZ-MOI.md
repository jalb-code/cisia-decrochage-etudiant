# Livrable — rejouer le notebook

**Certification IA** · Détection précoce du décrochage en L1 · Julien Alburquerque · Référentiel C1→C9.

Ce livrable contient le nécessaire pour **exécuter le notebook de bout en bout** et reproduire tous
les résultats. Il couvre les livrables obligatoires de l'énoncé (§5) : notebook, jeux de données
utilisés — **y compris le jeu préparé** — et scripts utilitaires de reproductibilité.

## Contenu

| Élément | Rôle |
|---|---|
| `notebooks/JALB-Decrochage-l1.ipynb` | Le livrable : notebook unique, plan imposé 0→15, avec ses sorties |
| `notebooks/JALB-JournalDeBord-Decrochage-l1.ipynb` | Journal de bord : suivi chronologique des sessions de travail |
| `JALB-Decrochage-l1.pptx` | Support de soutenance |
| `notebooks/ressources/*.png` | Illustrations affichées par les cellules (§10 déploiement, §11 architecture) |
| `data/raw/`, `data/sample/` | Jeux de données fournis et utilisés (voir `data/README.md`) |
| `data/gold/` | Jeu de référence préparé (§7.3), entrée de l'entraînement |
| `artifacts/` | Pipelines sérialisés, carte du modèle, métadonnées et contrat d'E/S (§10) |
| `reports/*.html` | Rapports de profilage des fichiers reçus (§5), source des constats de format |
| `src/decrochage_l1/` | Package appelé par le notebook (préparation, EDA, modélisation, serving) |
| `configs/pipeline_spec.json` | Jugements figés relus lors de l'industrialisation (§10) |
| `docs/registre-decisions.csv` | Registre des décisions : où chaque question est posée et tranchée |
| `pyproject.toml`, `uv.lock`, `.python-version` | Environnement figé (versions exactes) |

## Rejouer

```bash
uv sync --group analysis     # installe l'environnement exact (uv.lock)
```
Ouvrir `notebooks/JALB-Decrochage-l1.ipynb` puis **Run All**.

Le jeu préparé (`data/gold/`), les artefacts sérialisés (`artifacts/`) et les rapports de profilage
(`reports/*.html`) sont **fournis** ET **régénérés à l'identique** par le notebook depuis
`data/raw` : le livrable est autoportant, sans être une boîte noire.

## Projet complet

Le **projet complet** — service d'inférence (API), CLI d'industrialisation, conteneurs Docker,
supervision Prometheus/Grafana et suite de tests — est disponible sur GitHub :

**https://github.com/jalb-code/cisia-decrochage-etudiant**
