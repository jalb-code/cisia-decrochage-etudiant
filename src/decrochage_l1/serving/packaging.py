"""Emballage de l'artefact déployable à partir de la spec figée (§10, industrialisé).

Ce module **ré-exprime** pour la CLI ce que le notebook assemble en §10 : la fiche de service
(`ServiceContract`), la model card et ses métadonnées machine. Il transcrit les valeurs
déclarées au notebook (gouvernance de la carte, seuils de dérive, thèmes) depuis la spec, et
les valeurs mesurées (métriques du test scellé, empreinte du gold) depuis le ré-entraînement.
Il ne porte **aucun jugement** : tout vient de la spec (`data`/config) ou de la mesure.

La sérialisation elle-même reste déléguée aux modules partagés avec le notebook
(`serving.store.save_bundle`, `serving.model_card.save`) : ce module ne fait que **remplir**
leurs structures.
"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pandas as pd
from sklearn.pipeline import Pipeline

from decrochage_l1.modeling.spec import PipelineSpec
from decrochage_l1.serving import model_card, store
from decrochage_l1.serving.contract import ModelFacts, OperationalDefaults, ServiceContract


def package_version(distribution: str = "decrochage-l1") -> str:
    """Version installée du package, pour la traçabilité ; « inconnue » si non installé."""
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "inconnue"


def build_contract(
    spec: PipelineSpec, classifier: Pipeline, train: pd.DataFrame, *, threshold: float
) -> ServiceContract:
    """Assemble la fiche de service depuis la spec et le modèle entraîné (transcription §10.1).

    Le typage num/catégoriel sert la sélection des variables de dérive ; les thèmes,
    l'agrégation de l'explicabilité ; la distribution de référence (train scellé), la mesure
    de dérive de campagne. Les seuils d'exploitation viennent de la spec (défaut surchargeable).
    """
    model_features = list(classifier.feature_names_in_)
    numeric, ordinal, nominal = spec.feature_roles(list(train.columns))
    numeric_facts = [c for c in numeric if c in model_features]
    categorical_facts = [c for c in ordinal + nominal if c in model_features]
    themes = {c: spec.themes[c] for c in model_features if c in spec.themes}

    return ServiceContract(
        facts=ModelFacts(
            version=spec.version,
            numeric=tuple(numeric_facts),
            categorical=tuple(categorical_facts),
            themes=themes,
            drift_reference=train[model_features].copy(),
        ),
        defaults=OperationalDefaults(
            threshold=float(threshold),
            drift_surveillance=spec.drift_defaults["surveillance"],
            drift_alerte=spec.drift_defaults["alerte"],
            drift_effectif_min=spec.drift_defaults["effectif_min"],
        ),
    )


def build_card(
    spec: PipelineSpec,
    *,
    n_train_rows: int,
    abandon_rate: float,
    threshold: float,
    metrics_holdout: dict[str, float],
) -> model_card.ModelCard:
    """Compose la model card : gouvernance figée (spec) + chiffres mesurés (transcription §10.3)."""
    card = spec.model_card
    metrics = {
        "PR-AUC (abandon)": f"{metrics_holdout['pr_auc']:.3f}",
        "ROC-AUC (abandon)": f"{metrics_holdout['roc_auc']:.3f}",
        f"Rappel @seuil {threshold:.2f}": f"{metrics_holdout['rappel']:.0%}",
        f"Précision @seuil {threshold:.2f}": f"{metrics_holdout['precision']:.0%}",
        "Brier (fiabilité des probabilités)": f"{metrics_holdout['brier']:.4f}",
        "MAE note finale": f"{metrics_holdout['mae_note']:.2f} pts/20",
    }
    training_data = (
        f"Cohorte L1, jeu « gold » nettoyé et validé : {n_train_rows} étudiants au train, "
        f"{abandon_rate:.1%} d'abandons. Variables connues à mi-S1 uniquement, sans fuite "
        "temporelle. Attributs protégés (sexe, boursier) exclus du modèle, conservés hors modèle "
        "pour l'audit d'équité."
    )
    threshold_note = (
        f"{threshold:.2f}, fixé sur un plancher de rappel (le coût d'un décrocheur manqué dépasse "
        "celui d'une fausse alerte) ; paramètre d'exploitation, jamais figé dans les poids."
    )
    return model_card.ModelCard(
        model_name=card["model_name"],
        version=spec.version,
        created_at="",  # rempli par le paquet complet (date seule)
        owners=card["owners"],
        description=card["description"],
        details=card["details"],
        direct_use=card["direct_use"],
        users=card["users"],
        out_of_scope=card["out_of_scope"],
        limitations=card["limitations"],
        recommendations=card["recommendations"],
        training_data=training_data,
        evaluation_protocol=card["evaluation_protocol"],
        metrics=metrics,
        threshold_note=threshold_note,
        fairness_note=card["fairness_note"],
        technical_specs=card["technical_specs"],
        contact=card["contact"],
    )


def package(
    spec: PipelineSpec,
    *,
    classifier: Pipeline,
    regressor: Pipeline,
    train: pd.DataFrame,
    threshold: float,
    metrics_holdout: dict[str, float],
    created_at: str,
    artifacts_dir: Path,
    dataset: str,
    gold_md5: str,
) -> dict[str, Path]:
    """Écrit l'artefact complet (bundle + fiche + carte + métadonnées) et rend les chemins.

    Reproduit l'ensemble de §10 : sérialisation des deux pipelines et de la fiche, puis
    model card et métadonnées machine. `created_at`, `dataset` et `gold_md5` (empreinte du jeu)
    sont **passés** : le module ne lit ni horloge ni disque en son cœur.
    """
    contract = build_contract(spec, classifier, train, threshold=threshold)
    store.save_bundle(artifacts_dir, contract=contract, classifier=classifier, regressor=regressor)

    n_train_rows = len(train)
    abandon_rate = float(train[spec.target].astype(float).mean())

    metadata = model_card.build_metadata(
        version=spec.version,
        created_at=created_at,
        package_version=package_version(),
        random_seed=spec.seed,
        target_primary=spec.target,
        target_secondary=spec.target_secondary,
        features=list(classifier.feature_names_in_),
        n_train_rows=n_train_rows,
        abandon_rate_train=abandon_rate,
        dataset=dataset,
        gold_md5=gold_md5,
        threshold=threshold,
        metrics_holdout=metrics_holdout,
    )
    card = build_card(
        spec,
        n_train_rows=n_train_rows,
        abandon_rate=abandon_rate,
        threshold=threshold,
        metrics_holdout=metrics_holdout,
    )
    card.created_at = created_at[:10]  # date seule sur la carte lisible

    paths = model_card.save(artifacts_dir, card=card, metadata=metadata)
    return paths
