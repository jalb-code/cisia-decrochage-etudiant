from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from decrochage_l1.serving import metrics
from decrochage_l1.serving.api import create_app
from decrochage_l1.serving.settings import ServiceSettings
from decrochage_l1.serving.store import EntrepotModele

CLE = "secret"
HEAD = {"X-API-Key": CLE}


def _client(stub):
    entrepot = EntrepotModele()
    entrepot.load(stub.models_dir)
    service = ServiceSettings(api_keys=CLE, exposer_indicateur=True, monitoring_actif=False)
    return TestClient(create_app(entrepot=entrepot, service_settings=service))


def test_module_reflete_la_disponibilite():
    metrics.set_model_loaded(False)
    assert REGISTRY.get_sample_value("decrochage_modele_charge") == 0.0
    metrics.set_model_loaded(True)
    assert REGISTRY.get_sample_value("decrochage_modele_charge") == 1.0


def test_app_pose_les_jauges_au_demarrage(stub):
    _client(stub)  # la création de l'app pose disponibilité et seuil
    assert REGISTRY.get_sample_value("decrochage_modele_charge") == 1.0
    assert REGISTRY.get_sample_value("decrochage_seuil_defaut") == 0.16


def test_serie_de_refus_initialisee_a_zero(stub):
    _client(stub)
    # La série existe à 0 avant tout incident : sinon une alerte en increase() resterait muette.
    valeur = REGISTRY.get_sample_value(
        "decrochage_refus_perimetre_total", {"colonne": "moyenne_partiels_s1"}
    )
    assert valeur == 0.0


def test_compteur_incremente_sur_envoi_hors_perimetre(stub):
    client = _client(stub)
    label = {"colonne": "moyenne_partiels_s1"}
    avant = REGISTRY.get_sample_value("decrochage_refus_perimetre_total", label) or 0.0
    client.post("/v1/predict-etudiant", json=stub.dossier(moyenne_partiels_s1="12"), headers=HEAD)
    apres = REGISTRY.get_sample_value("decrochage_refus_perimetre_total", label)
    assert apres == avant + 1.0
