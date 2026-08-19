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
    assert corps["n_variables"] == 8  # 7 numériques + filière


def test_route_protegee_exige_une_cle(client):
    assert client.get("/v1/modele").status_code == 401
    assert client.get("/v1/modele", headers={"X-API-Key": "faux"}).status_code == 401
    assert client.get("/v1/modele", headers=HEAD).status_code == 200


def test_sans_cle_configuree_les_routes_protegees_repondent_503(stub):
    client = _client(stub, api_keys="")
    assert client.get("/v1/modele", headers=HEAD).status_code == 503


def test_fiche_publie_les_exclusions_motivees(client):
    fiche = client.get("/v1/modele", headers=HEAD).json()
    colonnes = {e["column"] for e in fiche["exclusions"]}
    assert "moyenne_partiels_s1" in colonnes
    assert fiche["seuil_defaut"] == 0.16
    assert "filiere" in fiche["nominal_modalities"]


def test_predict_etudiant_rend_proba_note_et_explicabilite(client, stub):
    corps = client.post("/v1/predict-etudiant", json=stub.dossier(), headers=HEAD).json()
    resultat = corps["resultat"]
    assert 0.0 <= resultat["probability"] <= 1.0
    assert 0.0 <= resultat["moyenne_finale"] <= 20.0
    assert resultat["contributions"]["by_theme"]
    assert corps["avertissement"]  # mention art. 22 systématique


def test_predict_etudiant_champ_interdit_refuse_422(client, stub):
    reponse = client.post(
        "/v1/predict-etudiant", json=stub.dossier(moyenne_partiels_s1="12"), headers=HEAD
    )
    assert reponse.status_code == 422
    champs = {e["field"] for e in reponse.json()["detail"]["errors"]}
    assert "moyenne_partiels_s1" in champs


def test_probabilite_independante_du_seuil(client, stub):
    dossier = stub.dossier()
    base = client.post("/v1/predict-etudiant", json=dossier, headers=HEAD).json()
    proba = base["resultat"]["probability"]
    # Deux seuils qui encadrent la probabilité mesurée : seul l'indicateur doit basculer.
    sous = client.post(f"/v1/predict-etudiant?seuil={proba}", json=dossier, headers=HEAD).json()
    sur = client.post(
        f"/v1/predict-etudiant?seuil={min(proba + 0.01, 1.0)}", json=dossier, headers=HEAD
    ).json()
    assert sous["resultat"]["probability"] == sur["resultat"]["probability"] == proba
    assert sous["resultat"]["signaled"] is True  # seuil == proba -> signalé (>=)
    assert sur["resultat"]["signaled"] is False  # seuil > proba -> non signalé
    assert sur["provenance_seuil"] == "appel"


def test_predict_cohorte_une_ligne_invalide_ne_bloque_pas_les_autres(client, stub):
    lot = {
        "dossiers": [
            stub.dossier(reference_dossier="ok-1"),
            stub.dossier(reference_dossier="ko", taux_presence_pct="150 %"),
            stub.dossier(reference_dossier="ok-2"),
        ]
    }
    corps = client.post("/v1/predict-cohorte", json=lot, headers=HEAD).json()
    # Ordre du lot restitué, la ligne invalide isolée avec son index.
    assert [r["reference"] for r in corps["resultats"]] == ["ok-1", "ok-2"]
    assert corps["refuses"][0]["index"] == 1
    assert corps["synthese"] == {
        "dossiers_recus": 3,
        "dossiers_scores": 2,
        "dossiers_refuses": 1,
        "part_signalee": corps["synthese"]["part_signalee"],
    }
    assert corps["resultats"][0]["contributions"]["by_variable"]  # facteurs principaux joints


def test_predict_cohorte_derive_en_option(client, stub):
    lot = {"dossiers": [stub.dossier(reference_dossier=f"r{i}") for i in range(220)]}
    sans = client.post("/v1/predict-cohorte", json=lot, headers=HEAD).json()
    assert "derive" not in sans
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
