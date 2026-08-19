import pytest
from fastapi.testclient import TestClient

from decrochage_l1.serving.api import create_app
from decrochage_l1.serving.settings import ServiceSettings
from decrochage_l1.serving.store import EntrepotModele

CLE = "secret"
HEAD = {"X-API-Key": CLE}


def _client(stub, **settings_overrides):
    entrepot = EntrepotModele()
    entrepot.load(stub.models_dir)
    params = {"api_keys": CLE, "exposer_indicateur": True, "monitoring_actif": False}
    params.update(settings_overrides)
    service = ServiceSettings(**params)
    return TestClient(create_app(entrepot=entrepot, service_settings=service))


@pytest.fixture
def client(stub):
    return _client(stub)


def test_health_ouvert_sans_cle(client):
    reponse = client.get("/health")
    assert reponse.status_code == 200
    assert reponse.json()["status"] == "ok"


def test_ready_expose_la_version(client):
    corps = client.get("/ready").json()
    assert corps["ready"] is True
    assert corps["version"] == "stub-1"
    assert corps["n_variables"] == 16  # 13 numériques (dont 2 dérivées) + 3 catégorielles


def test_route_protegee_exige_une_cle(client):
    assert client.get("/v1/modele").status_code == 401
    assert client.get("/v1/modele", headers={"X-API-Key": "faux"}).status_code == 401
    assert client.get("/v1/modele", headers=HEAD).status_code == 200


def test_sans_cle_configuree_les_routes_protegees_repondent_503(stub):
    client = _client(stub, api_keys="")
    assert client.get("/v1/modele", headers=HEAD).status_code == 503


def test_fiche_publie_le_descripteur(client):
    fiche = client.get("/v1/modele", headers=HEAD).json()
    assert fiche["seuil_defaut"] == 0.16
    assert "filiere" in fiche["categorical"]
    assert "taux_rendu" in fiche["numeric"]
    assert fiche["themes"]["filiere"] == "parcours"


def test_predict_etudiant_rend_proba_note_et_explicabilite(client, stub):
    corps = client.post("/v1/predict-etudiant", json=stub.dossier(), headers=HEAD).json()
    assert 0.0 <= corps["proba_abandon"] <= 1.0
    assert 0.0 <= corps["moyenne_finale"] <= 20.0
    assert corps["contributions_theme"]
    assert corps["contributions_variable"]  # détail par variable joint
    assert corps["version_modele"] == "stub-1"
    assert corps["avertissement"]  # mention art. 22 systématique


def test_predict_etudiant_champ_interdit_refuse_422(client, stub):
    reponse = client.post(
        "/v1/predict-etudiant", json={**stub.dossier(), "moyenne_partiels_s1": 12}, headers=HEAD
    )
    assert reponse.status_code == 422
    champs = {tuple(e["loc"])[-1] for e in reponse.json()["detail"]}
    assert "moyenne_partiels_s1" in champs


def test_predict_etudiant_valeur_hors_bornes_refuse_422(client, stub):
    reponse = client.post(
        "/v1/predict-etudiant", json=stub.dossier(taux_presence_pct=150.0), headers=HEAD
    )
    assert reponse.status_code == 422


def test_probabilite_independante_du_seuil(client, stub):
    dossier = stub.dossier()
    base = client.post("/v1/predict-etudiant", json=dossier, headers=HEAD).json()
    proba = base["proba_abandon"]
    # Deux seuils qui encadrent la probabilité mesurée : seul l'indicateur doit basculer.
    sous = client.post(f"/v1/predict-etudiant?seuil={proba}", json=dossier, headers=HEAD).json()
    sur = client.post(
        f"/v1/predict-etudiant?seuil={min(proba + 0.01, 1.0)}", json=dossier, headers=HEAD
    ).json()
    assert sous["proba_abandon"] == sur["proba_abandon"] == proba
    assert sous["signaled"] is True  # seuil == proba -> signalé (>=)
    assert sur["signaled"] is False  # seuil > proba -> non signalé
    assert sur["provenance_seuil"] == "appel"


def test_predict_cohorte_une_ligne_invalide_ne_bloque_pas_les_autres(client, stub):
    lot = {
        "dossiers": [
            stub.dossier(reference_dossier="ok-1"),
            stub.dossier(reference_dossier="ko", taux_presence_pct=150.0),
            stub.dossier(reference_dossier="ok-2"),
        ]
    }
    corps = client.post("/v1/predict-cohorte", json=lot, headers=HEAD).json()
    # Ordre du lot restitué, la ligne invalide isolée avec son index.
    assert [r["reference_dossier"] for r in corps["resultats"]] == ["ok-1", "ok-2"]
    assert corps["refuses"][0]["index"] == 1
    assert corps["synthese"]["dossiers_recus"] == 3
    assert corps["synthese"]["dossiers_scores"] == 2
    assert corps["synthese"]["dossiers_refuses"] == 1
    assert corps["resultats"][0]["contributions_theme"]  # facteurs par thème joints


def test_predict_cohorte_derive_en_option(client, stub):
    lot = {"dossiers": [stub.dossier(reference_dossier=f"r{i}") for i in range(220)]}
    sans = client.post("/v1/predict-cohorte", json=lot, headers=HEAD).json()
    assert sans["derive"] is None
    avec = client.post("/v1/predict-cohorte?derive=true", json=lot, headers=HEAD).json()
    assert avec["derive"]["mesurable"] is True


def test_derive_non_mesurable_sous_effectif(client, stub):
    lot = {"dossiers": [stub.dossier(reference_dossier=f"r{i}") for i in range(10)]}
    corps = client.post("/v1/predict-cohorte?derive=true", json=lot, headers=HEAD).json()
    assert corps["derive"]["mesurable"] is False


def test_lot_vide_refuse_422(client):
    assert (
        client.post("/v1/predict-cohorte", json={"dossiers": []}, headers=HEAD).status_code == 422
    )


def test_ecriture_du_seuil_refusee_405(client):
    # Aucune route n'écrit le seuil : une tentative reçoit 405 (seul GET est défini).
    assert client.post("/v1/seuil", headers=HEAD).status_code == 405


def test_seuil_en_vigueur_lu_dans_la_fiche(client):
    corps = client.get("/v1/seuil", headers=HEAD).json()
    assert corps["seuil"] == 0.16
    assert corps["provenance"] == "fiche"
    assert corps["exposer_indicateur"] is True
