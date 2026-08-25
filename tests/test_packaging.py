import json

import pytest

from decrochage_l1.config import settings
from decrochage_l1.modeling import pipeline
from decrochage_l1.modeling.spec import load_spec
from decrochage_l1.serving import model_card, packaging, store
from test_pipeline import gold_frame

METRICS = {
    "roc_auc": 0.9,
    "pr_auc": 0.8,
    "brier": 0.1,
    "rappel": 0.8,
    "precision": 0.7,
    "f1": 0.75,
    "f2": 0.78,
    "mae_note": 2.0,
    "rmse_note": 3.0,
    "r2_note": 0.6,
}


def test_package_ecrit_un_artefact_rechargeable(tmp_path):
    spec = load_spec()
    gold = gold_frame()
    feats = spec.features_min(list(gold.columns))
    clf = pipeline.build_classifier(spec, gold, feats).fit(gold[feats], gold["abandon"])
    reg = pipeline.build_regressor(spec, gold, feats).fit(gold[feats], gold["moyenne_finale"])

    artifacts = tmp_path / "artifacts"

    paths = packaging.package(
        spec,
        classifier=clf,
        regressor=reg,
        train=gold,
        threshold=0.42,
        metrics_holdout=METRICS,
        created_at="2026-08-20T10:00:00+00:00",
        artifacts_dir=artifacts,
        dataset="data/gold/etudiants_gold.csv",
        gold_md5="abc123def456",
    )

    assert (artifacts / store.CLASSIFIER_FILE).exists()
    assert (artifacts / store.REGRESSOR_FILE).exists()
    assert (artifacts / store.CONTRACT_FILE).exists()
    assert paths["card"].exists()
    assert paths["metadata"].exists()

    # L'artefact écrit se recharge et sert.
    entrepot = store.EntrepotModele()
    entrepot.load(artifacts)
    assert entrepot.ready is True
    assert list(entrepot.bundle.classifier.feature_names_in_) == feats

    meta = json.loads((artifacts / model_card.METADATA_FILE).read_text(encoding="utf-8"))
    assert meta["features"] == feats
    assert meta["threshold"] == 0.42
    assert meta["target"]["principale"] == "abandon"


def test_contract_porte_seuils_et_reference(tmp_path):
    spec = load_spec()
    gold = gold_frame()
    feats = spec.features_min(list(gold.columns))
    clf = pipeline.build_classifier(spec, gold, feats).fit(gold[feats], gold["abandon"])

    contract = packaging.build_contract(spec, clf, gold, threshold=0.42)
    assert contract.defaults.threshold == 0.42
    assert contract.defaults.drift_surveillance == 0.10
    assert contract.defaults.drift_alerte == 0.25
    assert contract.facts.drift_reference is not None
    assert list(contract.facts.drift_reference.columns) == feats
    # D45 : la référence embarquée est dé-identifiée (marginales mélangées, aucun dossier joint).
    assert contract.facts.drift_reference_shuffled is True
    jointes = gold[feats].merge(contract.facts.drift_reference, how="inner", on=feats)
    assert len(jointes) < len(gold)


def test_gouvernance_spec_ne_derive_pas_de_la_model_card_notebook():
    # Anti-divergence : la gouvernance figée dans la spec (§10, D44) doit se retrouver telle quelle
    # dans la model card produite par le notebook. Si l'une bouge sans l'autre, ce test casse -
    # même patron que normalization.add_derived vs preparation.build_gold.
    card_path = settings.artifacts_dir / model_card.CARD_FILE
    if not card_path.exists():
        pytest.skip(f"model card du notebook absente ({card_path}) - artefact hors dépôt")
    rendue = card_path.read_text(encoding="utf-8")

    gouvernance = load_spec().model_card
    textes = [
        gouvernance["model_name"],
        gouvernance["description"],
        gouvernance["direct_use"],
        gouvernance["users"],
        gouvernance["out_of_scope"],
        gouvernance["evaluation_protocol"],
        gouvernance["fairness_note"],
        gouvernance["technical_specs"],
        gouvernance["contact"],
        *gouvernance["limitations"],
        *gouvernance["recommendations"],
        *gouvernance["details"].values(),
    ]
    manquants = [t for t in textes if t not in rendue]
    assert not manquants, f"gouvernance spec absente de la model card notebook : {manquants}"
