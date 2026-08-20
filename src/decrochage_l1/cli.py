"""CLI `decrochage-l1` : rejouer la chaîne hors notebook — prédire, ré-entraîner (§13, C9).

Deux commandes, et deux seulement (D44) :

- **`predict`** — score un CSV de nouveaux dossiers (probabilité d'abandon + note estimée) à
  partir de l'artefact figé, sans rien ré-entraîner ;
- **`retrain`** — repart d'un nouveau jeu reçu et rejoue toute la chaîne
  bronze -> silver -> gold -> entraînement -> package, en **iso-périmètre** : mêmes jugements que
  ceux éprouvés au notebook, relus dans `configs/pipeline_spec.json`.

La CLI **n'optimise jamais les hyperparamètres** (D44) : ils sont gelés dans la spec ; un
re-réglage complet reste l'affaire du notebook (§9), là où il se défend. Chaque étape appelle
le code testé de `src/` ; la CLI n'est que l'orchestration, à la manière des cellules du
notebook (les doublons avec celui-ci sont assumés — industrialiser transcrit, ne refactore pas).
"""

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import typer

from decrochage_l1.config import settings
from decrochage_l1.data import preparation
from decrochage_l1.data.utils import profiling_utils, recoding_utils
from decrochage_l1.modeling import evaluation, pipeline, preprocessing, protocol, threshold
from decrochage_l1.modeling.spec import PipelineSpec, load_spec
from decrochage_l1.serving import normalization, packaging, scoring, store

app = typer.Typer(
    add_completion=False,
    help="Détection du décrochage L1 — prédire et ré-entraîner hors notebook (C9).",
)

GOLD_FILE = "etudiants_gold.csv"
SILVER_FILE = "etudiants_silver.csv"


def _declared_profile(columns: pd.Index, spec: PipelineSpec) -> pd.DataFrame:
    """Profil de types DÉCLARÉ (numérique -> décimal, sinon texte), sans inférence sur les données.

    Le schéma est connu (spec) : on ne le redécouvre pas à chaque fichier - une cohorte de
    quelques lignes pourrait mal typer une colonne et la conformer autrement qu'à l'entraînement.
    Les numériques passent en « décimal », jamais « entier » : « 67,2 % » ne doit pas être tronqué.
    """
    numeric = set(spec.numeric_columns)
    return pd.DataFrame(
        {
            "colonne": list(columns),
            "type_semantique": ["decimal" if c in numeric else "texte" for c in columns],
        }
    )


def _conform(csv_path: Path, spec: PipelineSpec) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lit un CSV reçu, le conforme sur des types DÉCLARÉS, recode, ajoute les dérivées.

    Rend le brut (textes tels que reçus, pour préserver les références) et le jeu conformé prêt à
    scorer. La lecture robuste (encodage, délimiteur) vient de `read_as_text` ; le typage vient de
    la spec, pas d'une inférence - `profile_csv` reste réservé à la découverte des données (§5).
    Pas de dédoublonnage : un dossier soumis = une ligne scorée.
    """
    raw, _ = profiling_utils.read_as_text(csv_path)
    profile = _declared_profile(raw.columns, spec)
    conformed = preparation.conform(raw, profile)
    recoded, _ = recoding_utils.recode(conformed, preparation.CANONICAL_MODALITIES)
    return raw, normalization.add_derived(recoded)


@app.command()
def predict(
    input_csv: Path = typer.Option(..., "--input", "-i", help="CSV des dossiers à scorer."),
    output_csv: Path = typer.Option(..., "--output", "-o", help="CSV des scores à écrire."),
    artifacts_dir: Path = typer.Option(
        None, "--artifacts", help="Dossier de l'artefact (défaut : settings.artifacts_dir)."
    ),
    indicator: bool = typer.Option(
        False, "--indicator", help="Exposer l'indicateur binaire (seuil de la fiche)."
    ),
) -> None:
    """Score un CSV de dossiers : probabilité d'abandon, note estimée, indicateur optionnel."""
    artifacts_dir = artifacts_dir or settings.artifacts_dir
    entrepot = store.EntrepotModele()
    entrepot.load(artifacts_dir)
    if not entrepot.ready:
        typer.echo(f"Artefact indisponible : {entrepot.error}", err=True)
        raise typer.Exit(code=1)
    bundle = entrepot.bundle

    raw, accepted = _conform(input_csv, load_spec())
    model_features = list(bundle.classifier.feature_names_in_)
    missing = [c for c in model_features if c not in accepted.columns]
    if missing:
        typer.echo(f"Colonnes manquantes pour le modèle : {missing}", err=True)
        raise typer.Exit(code=1)

    # Références lues sur le brut (casse d'origine préservée), alignées ligne à ligne (pas de
    # dédoublonnage : un dossier soumis = une ligne scorée).
    id_columns = [c for c in ("reference_dossier", "student_id", "id_dossier") if c in raw.columns]
    references: list[str | None] = (
        raw[id_columns[0]].astype(str).tolist() if id_columns else [None] * len(accepted)
    )
    scores = scoring.score(
        bundle,
        accepted,
        references,
        threshold=bundle.contract.defaults.threshold,
        expose_indicator=indicator,
    )
    frame = pd.DataFrame(
        {
            "reference": [s.reference for s in scores],
            "probability": [round(s.probability, 4) for s in scores],
            "moyenne_finale": [round(s.moyenne_finale, 2) for s in scores],
            "signaled": [s.signaled for s in scores],
        }
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_csv, index=False)
    typer.echo(f"{len(frame)} dossiers scorés -> {output_csv}")


def _fit_models(
    spec: PipelineSpec, train: pd.DataFrame, features: list[str], cv: object
) -> tuple[object, object, float]:
    """Ajuste les deux pipelines sur le train et fixe le seuil sur les probabilités OOF."""
    x_train = train[features]
    y_train = train[spec.target].astype(int)
    y_note = train[spec.target_secondary]

    classifier = pipeline.build_classifier(spec, train, features)
    proba_oof = evaluation.oof_proba(classifier, x_train, y_train, cv)
    decision_threshold = threshold.pick_threshold(
        y_train, proba_oof, recall_target=spec.recall_target
    )

    classifier.fit(x_train, y_train)
    regressor = pipeline.build_regressor(spec, train, features)
    regressor.fit(x_train, y_note)
    return classifier, regressor, float(decision_threshold)


def _holdout_metrics(
    spec: PipelineSpec,
    classifier: object,
    regressor: object,
    test: pd.DataFrame,
    features: list[str],
    decision_threshold: float,
) -> dict[str, float]:
    """Mesure sur le test scellé les métriques figées dans les métadonnées (§12.1-12.3)."""
    x_test = test[features]
    y_test = test[spec.target].astype(int)
    y_test_note = test[spec.target_secondary]

    proba_test = classifier.predict_proba(x_test)[:, 1]
    clf_metrics = evaluation.classification_metrics(y_test, proba_test)
    point = threshold.threshold_table(
        y_test, proba_test, thresholds=np.array([decision_threshold])
    ).iloc[0]
    rappel, precision = float(point["rappel"]), float(point["precision"])
    f1 = 2 * precision * rappel / (precision + rappel) if (precision + rappel) else 0.0

    pred_note = np.clip(regressor.predict(x_test), 0.0, 20.0)
    reg_metrics = evaluation.regression_metrics(y_test_note, pred_note)

    return {
        "roc_auc": clf_metrics["roc_auc"],
        "pr_auc": clf_metrics["pr_auc"],
        "brier": clf_metrics["brier"],
        "rappel": rappel,
        "precision": precision,
        "f1": f1,
        "f2": float(point["f2"]),
        "mae_note": reg_metrics["mae"],
        "rmse_note": reg_metrics["rmse"],
        "r2_note": reg_metrics["r2"],
    }


@app.command()
def retrain(
    students_csv: Path = typer.Option(
        ..., "--students", "-s", help="Nouveau jeu étudiants (CSV reçu)."
    ),
    spec_path: Path = typer.Option(None, "--spec", help="Spec figée (défaut : configs/)."),
    artifacts_dir: Path = typer.Option(
        None, "--artifacts", help="Dossier de sortie de l'artefact (défaut : settings)."
    ),
    save_paliers: bool = typer.Option(
        True,
        "--save-paliers/--no-save-paliers",
        help="Écrire bronze/silver/gold sous data/ (traçabilité) ou non.",
    ),
) -> None:
    """Rejoue bronze->silver->gold->entraînement->package sur un nouveau jeu, à iso-périmètre."""
    spec = load_spec(spec_path)
    artifacts_dir = artifacts_dir or settings.artifacts_dir

    # --- silver : conformation (types déclarés), recodage, dédoublonnage ---
    raw, _ = profiling_utils.read_as_text(students_csv)
    silver, transfo = preparation.transform(raw, _declared_profile(raw.columns, spec))

    # --- gold : exclusions de principe + features dérivées ; empreinte calculée en mémoire ---
    gold, gold_result = preparation.build_gold(silver, spec.gold_exclusions)
    gold_csv = gold.to_csv(index=False)
    gold_md5 = hashlib.md5(gold_csv.encode("utf-8")).hexdigest()[:12]  # empreinte, non crypto

    if save_paliers:
        settings.bronze_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(students_csv, settings.bronze_dir / Path(students_csv).name)
        settings.silver_dir.mkdir(parents=True, exist_ok=True)
        silver.to_csv(settings.silver_dir / SILVER_FILE, index=False)
        settings.gold_dir.mkdir(parents=True, exist_ok=True)
        (settings.gold_dir / GOLD_FILE).write_text(gold_csv, encoding="utf-8")
    typer.echo(
        f"gold : {gold_result.n_rows} lignes × {gold_result.n_columns} colonnes "
        f"({transfo.n_duplicates_removed} doublons retirés)"
        + ("" if save_paliers else " · paliers non enregistrés")
    )

    # --- entraînement : dtypes numpy (équivalent d'une relecture CSV), split scellé, fit ---
    gold_df = preprocessing.to_numpy_dtypes(gold)
    gold_df[spec.target] = gold_df[spec.target].astype(int)
    features = spec.features_min(list(gold_df.columns))
    train_df, test_df = protocol.make_split(
        gold_df, spec.target, test_size=spec.test_size, seed=spec.seed
    )
    cv = protocol.make_cv(n_splits=spec.n_splits, seed=spec.seed)
    classifier, regressor, decision_threshold = _fit_models(spec, train_df, features, cv)
    metrics_holdout = _holdout_metrics(
        spec, classifier, regressor, test_df, features, decision_threshold
    )
    typer.echo(
        f"test scellé : ROC-AUC {metrics_holdout['roc_auc']:.3f} · "
        f"rappel {metrics_holdout['rappel']:.1%} @seuil {decision_threshold:.2f}"
    )

    # --- package : bundle + fiche + carte + métadonnées ---
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    dataset = (settings.gold_dir / GOLD_FILE).relative_to(settings.root_dir).as_posix()
    paths = packaging.package(
        spec,
        classifier=classifier,
        regressor=regressor,
        train=train_df,
        threshold=decision_threshold,
        metrics_holdout=metrics_holdout,
        created_at=created_at,
        artifacts_dir=artifacts_dir,
        dataset=dataset,
        gold_md5=gold_md5,
    )
    typer.echo(f"artefact écrit dans {artifacts_dir} · carte {paths['card'].name}")


if __name__ == "__main__":
    app()
