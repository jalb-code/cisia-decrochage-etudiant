"""Le schéma d'entrée `PredictEtudiantForm` fait foi ; ces tests en gardent le comportement
et vérifient qu'il **ne diverge pas** des features du modèle (via le stub).
"""

import pytest
from pydantic import ValidationError

from conftest import DERIVED, MODEL_FEATURES
from decrochage_l1.serving import schemas

VALIDE = {
    "age": 19,
    "filiere": "informatique",
    "bac_type": "general",
    "taux_presence_pct": 82.0,
    "heures_lms_total": 40.0,
    "nb_ue_total": 6,
    "nb_devoirs_total": 10,
    "nb_devoirs_rendus": 8,
    "retards_rendus": 1,
    "messages_forum": 3,
}


def test_dossier_valide_accepte():
    form = schemas.PredictEtudiantForm(**VALIDE)
    assert form.motivation is None  # optionnel omis reste None (imputé plus loin)


def test_champ_inconnu_refuse():
    with pytest.raises(ValidationError):
        schemas.PredictEtudiantForm(**VALIDE, moyenne_partiels_s1=12)


def test_borne_depassee_refuse():
    with pytest.raises(ValidationError):
        schemas.PredictEtudiantForm(**{**VALIDE, "taux_presence_pct": 150})


def test_modalite_inconnue_refuse():
    with pytest.raises(ValidationError):
        schemas.PredictEtudiantForm(**{**VALIDE, "filiere": "philosophie"})


def test_incoherence_rendus_superieurs_au_total_refuse():
    with pytest.raises(ValidationError, match="nb_devoirs_rendus"):
        schemas.PredictEtudiantForm(**{**VALIDE, "nb_devoirs_rendus": 20})


def test_champs_du_schema_couvrent_les_features_du_modele():
    # Non-écart : champs d'entrée du schéma == features du modèle moins les dérivées.
    attendu = set(MODEL_FEATURES) - set(DERIVED)
    assert set(schemas.INPUT_FIELDS) == attendu
