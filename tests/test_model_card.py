import json

from decrochage_l1.serving import model_card


def _card() -> model_card.ModelCard:
    return model_card.ModelCard(
        model_name="Décrochage L1",
        version="1.0.0",
        created_at="2026-08-20T00:00:00+00:00",
        owners="Établissement (responsable de traitement)",
        description="Modèle d'aide à la décision qui estime la probabilité d'abandon en L1.",
        details={"Type": "régression logistique calibrée", "Langue": "français"},
        direct_use="Prioriser l'accompagnement des étudiants de L1 à mi-S1.",
        users="Cellule pédagogique.",
        out_of_scope="Aucune décision administrative automatisée (art. 22).",
        limitations=["Cohorte d'un seul établissement."],
        recommendations=["Suivre la dérive par campagne et demander un ré-entraînement."],
        training_data="Cohorte L1, jeu gold nettoyé et validé.",
        evaluation_protocol="Test scellé (20 %), une seule passe.",
        metrics={"PR-AUC": "0.61", "Rappel @0.42": "0.74"},
        threshold_note="0,42, fixé sur un plancher de rappel.",
        fairness_note="Rappel comparable entre sexes et statuts boursiers.",
        technical_specs="Pipeline scikit-learn sérialisé, servi par une API FastAPI.",
        contact="Établissement (cellule pédagogique).",
    )


def test_render_card_porte_les_sections_et_les_metriques():
    rendu = model_card.render_card(_card())
    for titre in ("Détails du modèle", "Données d'entraînement", "Évaluation", "Biais, risques"):
        assert titre in rendu
    assert "PR-AUC" in rendu and "0.61" in rendu  # une métrique passée se retrouve dans la carte
    assert "test scellé" in rendu.lower()  # terminologie retenue, pas « hors échantillon »


def test_bullets_liste_vide_ecrit_aucun():
    assert model_card._bullets([]) == "_Aucun._"
    assert "- a" in model_card._bullets(["a", "b"])


def test_build_metadata_arrondit_et_structure_les_cibles():
    meta = model_card.build_metadata(
        version="1.0.0",
        created_at="2026-08-20T00:00:00+00:00",
        package_version="0.1.0",
        random_seed=42,
        target_primary="abandon",
        target_secondary="moyenne_finale",
        features=["taux_presence_pct", "taux_rendu"],
        n_train_rows=1676,
        abandon_rate_train=0.099234,
        dataset="data/gold/gold.csv",
        gold_md5="504da70e14a0",
        threshold=0.4213,
        metrics_holdout={"pr_auc": 0.61239},
    )
    assert meta["target"] == {"principale": "abandon", "secondaire": "moyenne_finale"}
    assert meta["abandon_rate_train"] == 0.0992  # arrondi à 4 décimales
    assert meta["metrics_holdout"]["pr_auc"] == 0.6124


def test_save_ecrit_les_deux_livrables(tmp_path):
    meta = {"version": "1.0.0", "features": ["a"]}
    chemins = model_card.save(tmp_path / "artifacts", card=_card(), metadata=meta)
    assert chemins["card"].name == "model_card.md"
    assert chemins["metadata"].name == "model_metadata.json"
    assert "Model card" in chemins["card"].read_text(encoding="utf-8")
    assert json.loads(chemins["metadata"].read_text(encoding="utf-8"))["version"] == "1.0.0"
