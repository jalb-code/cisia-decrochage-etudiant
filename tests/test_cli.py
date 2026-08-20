import numpy as np
import pandas as pd
from typer.testing import CliRunner

from conftest import MODEL_FEATURES
from decrochage_l1.cli import app
from decrochage_l1.config import settings
from decrochage_l1.serving import store

runner = CliRunner()

MENTIONS = ("passable", "assez bien", "bien", "tres bien")
FILIERES = ("biologie", "droit", "gestion", "informatique", "lettres", "psychologie")
BAC_TYPES = ("general", "technologique", "professionnel")
ETABLISSEMENTS = ("lycee_public", "lycee_prive", "cfa", "autre")


def full_raw_frame(n: int = 240) -> pd.DataFrame:
    # Jeu brut synthétique complet : toutes les colonnes reçues, avant mise en forme, avec les
    # exclusions de principe et les blocs d'ablation - de quoi exercer bronze -> gold -> package.
    rng = np.random.default_rng(1)
    total = rng.integers(5, 20, n)
    rendus = np.minimum(total, rng.integers(0, 20, n))
    retards = np.minimum(rendus, rng.integers(0, 10, n))
    presence = rng.uniform(30, 100, n)
    jours = rng.integers(1, 28, n)
    return pd.DataFrame(
        {
            "student_id": [f"etu-{i:05d}" for i in range(n)],
            "id_dossier": [f"dos-{i:05d}" for i in range(n)],
            "annee_universitaire": "2023-2024",
            "commentaire_tuteur": "",
            "date_inscription": [f"2024-09-{d:02d}" for d in jours],
            "sexe": rng.choice(("femme", "homme"), n),
            "boursier": rng.choice(("oui", "non"), n),
            "age": rng.integers(17, 25, n),
            "taux_presence_pct": presence.round(1),
            "heures_lms_total": rng.uniform(0, 120, n).round(1),
            "retards_rendus": retards,
            "nb_devoirs_total": total,
            "nb_devoirs_rendus": rendus,
            "messages_forum": rng.integers(0, 15, n),
            "nb_ue_total": rng.integers(5, 8, n),
            "motivation": rng.integers(1, 6, n),
            "satisfaction": rng.integers(1, 6, n),
            "sentiment_appartenance": rng.integers(1, 6, n),
            "heures_travail_remunere_sem": rng.integers(0, 20, n),
            "distance_domicile_km": rng.uniform(0, 60, n).round(1),
            "connexions_lms_30j": rng.integers(0, 40, n),
            "ressources_consultees": rng.integers(0, 80, n),
            "moyenne_partiels_s1": rng.uniform(0, 20, n).round(1),
            "nb_ue_validees_s1": rng.integers(0, 8, n),
            "mention_bac": rng.choice(MENTIONS, n),
            "filiere": rng.choice(FILIERES, n),
            "bac_type": rng.choice(BAC_TYPES, n),
            "etablissement_origine": rng.choice(ETABLISSEMENTS, n),
            "groupe_td": rng.choice(list("abcdefgh"), n),
            "couleur_carte_etudiante": rng.choice(("bleu", "gris", "jaune", "rouge", "vert"), n),
            "jour_inscription": rng.choice(("lundi", "mardi", "mercredi", "jeudi", "vendredi"), n),
            "abandon": (presence < 60).astype(int),
            "moyenne_finale": np.clip(4 + 0.12 * presence, 0, 20).round(1),
        }
    )


def test_predict_produit_des_scores(stub, tmp_path):
    # Dossiers d'entrée : les features brutes (les dérivées sont recalculées par la CLI).
    raw = stub.training.drop(columns=["taux_rendu", "ratio_retards"]).head(50)
    input_csv = tmp_path / "dossiers.csv"
    raw.to_csv(input_csv, index=False)
    output_csv = tmp_path / "scores.csv"

    result = runner.invoke(
        app,
        [
            "predict",
            "--input",
            str(input_csv),
            "--output",
            str(output_csv),
            "--artifacts",
            str(stub.artifacts_dir),
            "--indicator",
        ],
    )
    assert result.exit_code == 0, result.output

    scores = pd.read_csv(output_csv)
    assert list(scores.columns) == ["reference", "probability", "moyenne_finale", "signaled"]
    assert len(scores) > 0
    assert ((scores["probability"] >= 0) & (scores["probability"] <= 1)).all()
    assert ((scores["moyenne_finale"] >= 0) & (scores["moyenne_finale"] <= 20)).all()


def test_predict_artefact_absent_code_erreur(tmp_path):
    input_csv = tmp_path / "dossiers.csv"
    pd.DataFrame({"age": [19]}).to_csv(input_csv, index=False)
    result = runner.invoke(
        app,
        [
            "predict",
            "--input",
            str(input_csv),
            "--output",
            str(tmp_path / "out.csv"),
            "--artifacts",
            str(tmp_path / "vide"),
        ],
    )
    assert result.exit_code == 1
    assert "indisponible" in result.output


def test_retrain_produit_un_artefact_rechargeable(tmp_path, monkeypatch):
    # Racine des données redirigée : bronze/silver/gold vont dans le tmp, jamais dans le dépôt.
    monkeypatch.setattr(settings, "root_dir", tmp_path)
    students = tmp_path / "jeu_recu.csv"
    full_raw_frame().to_csv(students, index=False)
    artifacts = tmp_path / "artifacts"

    result = runner.invoke(
        app, ["retrain", "--students", str(students), "--artifacts", str(artifacts)]
    )
    assert result.exit_code == 0, result.output

    # Les trois paliers et l'artefact sont écrits sous la racine redirigée.
    assert (tmp_path / "data" / "gold" / "etudiants_gold.csv").exists()
    entrepot = store.EntrepotModele()
    entrepot.load(artifacts)
    assert entrepot.ready is True
    # Le modèle ré-entraîné porte bien les 16 features minimisées.
    assert len(entrepot.bundle.classifier.feature_names_in_) == len(MODEL_FEATURES)
