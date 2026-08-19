import pandas as pd

from decrochage_l1.serving import validation
from decrochage_l1.serving.contract import Bound, CoherenceRule, ModelFacts, OperationalDefaults

FACTS = ModelFacts(
    version="v",
    input_columns=("taux_presence_pct", "nb_devoirs_total", "nb_devoirs_rendus", "filiere"),
    derived_columns=("taux_rendu",),
    numeric=("taux_presence_pct", "nb_devoirs_total", "nb_devoirs_rendus", "taux_rendu"),
    categorical=("filiere",),
    nominal_modalities={"filiere": ("biologie", "droit", "informatique")},
    exclusions=(),
    themes={},
    units={"taux_presence_pct": ("%",)},
)

DEFAULTS = OperationalDefaults(
    threshold=0.16,
    bounds={"taux_presence_pct": Bound(0, 100), "nb_devoirs_total": Bound(1, 50)},
    coherence=(CoherenceRule("nb_devoirs_rendus", "nb_devoirs_total"),),
    drift_surveillance=0.10,
    drift_alerte=0.25,
    drift_effectif_min=200,
)


def _dossier(**overrides) -> dict:
    base = {
        "reference_dossier": "ref-0",
        "taux_presence_pct": "85 %",
        "nb_devoirs_total": "10",
        "nb_devoirs_rendus": "8",
        "filiere": "Informatique",
    }
    base.update(overrides)
    return base


def test_dossier_valide_accepte_et_conforme():
    res = validation.validate([_dossier()], FACTS, DEFAULTS)
    assert res.rejections == ()
    assert len(res.accepted) == 1
    ligne = res.accepted.iloc[0]
    assert ligne["taux_presence_pct"] == 85.0  # « % » retiré, typé nombre
    assert ligne["filiere"] == "informatique"  # normalisée
    assert ligne["taux_rendu"] == 0.8  # dérivée calculée par le service
    assert res.accepted_references == ["ref-0"]


def test_champ_hors_perimetre_refuse_en_nommant_le_champ():
    res = validation.validate([_dossier(moyenne_partiels_s1="12")], FACTS, DEFAULTS)
    assert len(res.rejections) == 1
    champs = {e.field for e in res.rejections[0].errors}
    assert "moyenne_partiels_s1" in champs


def test_variable_derivee_transmise_refusee():
    res = validation.validate([_dossier(taux_rendu="0.9")], FACTS, DEFAULTS)
    motifs = {(e.field, e.message) for e in res.rejections[0].errors}
    assert any(champ == "taux_rendu" and "dérivée" in message for champ, message in motifs)


def test_valeur_hors_bornes_refusee():
    res = validation.validate([_dossier(taux_presence_pct="150 %")], FACTS, DEFAULTS)
    champs = {e.field for e in res.rejections[0].errors}
    assert "taux_presence_pct" in champs


def test_incoherence_inter_champs_refusee():
    # rendus (12) > total (10) : incohérence, refus explicite.
    res = validation.validate(
        [_dossier(nb_devoirs_rendus="12", nb_devoirs_total="10")], FACTS, DEFAULTS
    )
    champs = {e.field for e in res.rejections[0].errors}
    assert "nb_devoirs_rendus" in champs


def test_modalite_inconnue_refusee():
    res = validation.validate([_dossier(filiere="Alchimie")], FACTS, DEFAULTS)
    champs = {e.field for e in res.rejections[0].errors}
    assert "filiere" in champs


def test_valeur_manquante_acceptee():
    # Une cellule vide est une absence, pas une erreur : la ligne passe (imputée plus loin).
    res = validation.validate([_dossier(taux_presence_pct="")], FACTS, DEFAULTS)
    assert res.rejections == ()
    assert pd.isna(res.accepted.iloc[0]["taux_presence_pct"])


def test_lot_mixte_une_ligne_invalide_ne_bloque_pas_les_autres():
    lot = [
        _dossier(reference_dossier="ok-1"),
        _dossier(reference_dossier="ko", taux_presence_pct="150 %"),
        _dossier(reference_dossier="ok-2"),
    ]
    res = validation.validate(lot, FACTS, DEFAULTS)
    assert len(res.accepted) == 2
    assert res.accepted_references == ["ok-1", "ok-2"]
    assert len(res.rejections) == 1
    assert res.rejections[0].index == 1
    assert res.rejections[0].reference == "ko"
