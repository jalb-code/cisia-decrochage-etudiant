"""Carte du modèle (§12) : rend la model card lisible et ses métadonnées machine.

Deux livrables jumeaux, écrits dans `artifacts/` :

- **`model_card.md`** — la carte que lisent le client et l'auditeur : usage prévu, données,
  métriques, limites, risques éthiques, version (structure façon *Hugging Face model card*).
- **`model_metadata.json`** — le jumeau lisible-machine : features, seuil, empreinte du jeu
  gold, métriques hors échantillon. C'est ce qu'un pipeline de ré-entraînement compare d'une
  version à l'autre.

Le module porte la **structure** de ces deux livrables et leur sérialisation. Il ne porte
**aucun jugement** : usage prévu, limites, risques éthiques et valeurs de métriques sont
DÉCLARÉS au notebook (§2, §4, §12) et passés en paramètres — c'est là qu'ils se défendent à
l'oral. Aucune table de jugement n'est codée ici.
"""

import json
from dataclasses import dataclass
from pathlib import Path

CARD_FILE = "model_card.md"
METADATA_FILE = "model_metadata.json"


@dataclass
class ModelCard:
    """Contenu de la model card — déclaré au notebook, rendu en Markdown par ce module.

    Structure calquée sur le *template Hugging Face model card* (Détails, Usages, Biais/risques
    /limites, Données, Évaluation, Spécifications), élaguée des sections sans objet ici. Livrable
    **autonome** : le texte déclaré ne renvoie à aucune section du notebook.
    """

    model_name: str
    version: str
    created_at: str  # ISO 8601, fourni par le notebook (reproductibilité)
    owners: str  # responsable de traitement / équipe
    description: str  # présentation du modèle (Détails du modèle)
    details: dict[str, str]  # label -> valeur : développé par, type, cibles, langue, licence
    direct_use: str  # usage direct visé (finalité)
    users: str  # utilisateurs visés
    out_of_scope: str  # usages hors périmètre (ce que le modèle ne doit pas servir)
    limitations: list[str]  # biais, risques et limites connus
    recommendations: list[str]  # recommandations d'usage et de suivi
    training_data: str  # description des données d'entraînement
    evaluation_protocol: str  # protocole d'évaluation (test scellé, une passe)
    metrics: dict[str, str]  # nom lisible -> valeur déjà formatée (test scellé)
    threshold_note: str  # seuil de décision et sa justification en une clause
    fairness_note: str  # synthèse de l'audit d'équité
    technical_specs: str  # architecture et service (une à deux phrases)
    contact: str  # point de contact / responsable


def _bullets(items: list[str]) -> str:
    """Rend une liste de puces Markdown, ou « _Aucun._ » si la liste est vide."""
    return "\n".join(f"- {item}" for item in items) if items else "_Aucun._"


def _detail_bullets(details: dict[str, str]) -> str:
    """Rend un dictionnaire label -> valeur en puces `**label** — valeur`."""
    return "\n".join(f"- **{label}** — {value}" for label, value in details.items())


def render_card(card: ModelCard) -> str:
    """Rend la model card en Markdown (structure façon Hugging Face model card)."""
    metrics = "\n".join(f"| {name} | {value} |" for name, value in card.metrics.items())
    entete = (
        f"**Version** {card.version} · **Date** {card.created_at} · "
        f"**Responsable de traitement** {card.owners}"
    )
    return f"""# Model card — {card.model_name}

{entete}

## Détails du modèle

{card.description}

{_detail_bullets(card.details)}

## Usages

**Usage direct.** {card.direct_use}

**Utilisateurs visés.** {card.users}

**Hors périmètre.** {card.out_of_scope}

## Biais, risques et limites

{_bullets(card.limitations)}

**Recommandations.**

{_bullets(card.recommendations)}

## Données d'entraînement

{card.training_data}

## Évaluation

{card.evaluation_protocol}

**Métriques sur le test scellé.**

| Métrique | Valeur |
|---|---|
{metrics}

**Seuil de décision.** {card.threshold_note}

**Équité.** {card.fairness_note}

## Spécifications techniques

{card.technical_specs}

## Contact

{card.contact}
"""


def build_metadata(
    *,
    version: str,
    created_at: str,
    package_version: str,
    random_seed: int,
    target_primary: str,
    target_secondary: str,
    features: list[str],
    n_train_rows: int,
    abandon_rate_train: float,
    dataset: str,
    gold_md5: str,
    threshold: float,
    metrics_holdout: dict[str, float],
) -> dict:
    """Construit le dictionnaire de métadonnées machine (jumeau de la model card)."""
    return {
        "created_at": created_at,
        "package_version": package_version,
        "random_seed": random_seed,
        "version": version,
        "target": {"principale": target_primary, "secondaire": target_secondary},
        "features": list(features),
        "n_train_rows": n_train_rows,
        "abandon_rate_train": round(abandon_rate_train, 4),
        "dataset": dataset,
        "gold_md5": gold_md5,
        "threshold": round(threshold, 4),
        "metrics_holdout": {k: round(v, 4) for k, v in metrics_holdout.items()},
    }


def save(artifacts_dir: Path, *, card: ModelCard, metadata: dict) -> dict[str, Path]:
    """Écrit la model card (`.md`) et ses métadonnées (`.json`) ; renvoie leurs chemins."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    card_path = artifacts_dir / CARD_FILE
    meta_path = artifacts_dir / METADATA_FILE
    card_path.write_text(render_card(card), encoding="utf-8")
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"card": card_path, "metadata": meta_path}
