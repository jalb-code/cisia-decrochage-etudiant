"""Service d'inférence (§11) — FastAPI, deux routes de prédiction et les sondes.

Cinq principes tenus par le code :

- **la sortie principale est une probabilité**, pas une classe ; l'indicateur « signalé »
  n'apparaît que si l'exploitation l'expose, et le seuil est un **paramètre** (fiche, ou
  surcharge d'environnement, ou `?seuil=` d'un appel), jamais dans les poids ;
- **le service ne conserve rien** — aucune écriture, aucune base ;
- **le refus de fuite est structurel** — un champ hors périmètre est refusé en le nommant ;
- **`/health` dit si le processus vit, `/ready` si le modèle est utilisable** — deux sondes
  distinctes ;
- **le modèle est chargé une fois**, au démarrage, via l'entrepôt injecté.

Chaque réponse porte l'avertissement de l'article 22 : aide à la décision, la décision reste
humaine. La route `/v1/predict-cohorte` est la principale (le régime réel est une campagne) ;
`/v1/predict-etudiant` sert le test ponctuel d'un dossier.
"""

from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from decrochage_l1.config import settings as runtime_settings
from decrochage_l1.serving import schemas, scoring, validation
from decrochage_l1.serving.contract import ServiceContract
from decrochage_l1.serving.settings import ServiceSettings
from decrochage_l1.serving.store import Bundle, EntrepotModele

TOP_CONTRIBUTIONS_CAMPAGNE = 5  # une campagne n'expose que les facteurs principaux par ligne


def _resolve_threshold(
    seuil: float | None, service: ServiceSettings, contract: ServiceContract
) -> float:
    """Seuil effectif : l'appel prime, puis la configuration, puis le défaut de la fiche."""
    if seuil is not None:
        value = seuil
    elif service.seuil_defaut is not None:
        value = service.seuil_defaut
    else:
        value = contract.defaults.threshold
    if not 0.0 <= value <= 1.0:
        raise HTTPException(status_code=422, detail=f"seuil hors [0, 1] : {value}")
    return value


def _threshold_provenance(seuil: float | None, service: ServiceSettings) -> str:
    """D'où vient le seuil effectif — pour que l'appelant sache ce qui s'applique."""
    if seuil is not None:
        return "appel"
    return "configuration" if service.seuil_defaut is not None else "fiche"


def create_app(
    *, entrepot: EntrepotModele | None = None, service_settings: ServiceSettings | None = None
) -> FastAPI:
    """Assemble l'application, entrepôt et réglages **injectables** (tests) ou lus par défaut."""
    service = service_settings or ServiceSettings()
    if entrepot is None:
        entrepot = EntrepotModele()
        entrepot.load(runtime_settings.models_dir)

    app = FastAPI(title="Décrochage L1 — service d'inférence", version="1")
    app.state.settings = service
    app.state.entrepot = entrepot

    if service.origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=service.origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def require_api_key(
        request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")
    ) -> None:
        keys = request.app.state.settings.allowed_keys
        if not keys:
            raise HTTPException(status_code=503, detail="contrôle d'accès non configuré")
        if x_api_key is None or x_api_key not in keys:
            raise HTTPException(status_code=401, detail="clé d'API absente ou invalide")

    def require_ready(request: Request) -> Bundle:
        entrepot_local: EntrepotModele = request.app.state.entrepot
        if not entrepot_local.ready:
            raise HTTPException(
                status_code=503, detail=f"modèle indisponible : {entrepot_local.error}"
            )
        return entrepot_local.bundle

    @app.post("/v1/predict-cohorte")
    def predict_cohorte(
        request: Request,
        payload: schemas.CampaignRequest,
        seuil: float | None = Query(default=None),
        derive: bool = Query(default=False),
        _: None = Depends(require_api_key),
        bundle: Bundle = Depends(require_ready),
    ) -> dict:
        service_local: ServiceSettings = request.app.state.settings
        threshold = _resolve_threshold(seuil, service_local, bundle.contract)
        result = validation.validate(
            payload.dossiers, bundle.contract.facts, bundle.contract.defaults
        )
        scores = scoring.score(
            bundle,
            result.accepted,
            result.accepted_references,
            threshold=threshold,
            expose_indicator=service_local.exposer_indicateur,
        )
        part_signalee = None
        if service_local.exposer_indicateur and scores:
            part_signalee = sum(1 for s in scores if s.signaled) / len(scores)

        body = {
            "seuil_applique": threshold,
            "provenance_seuil": _threshold_provenance(seuil, service_local),
            "resultats": [schemas.score_to_dict(s, top=TOP_CONTRIBUTIONS_CAMPAGNE) for s in scores],
            "refuses": [schemas.rejection_to_dict(r) for r in result.rejections],
            "synthese": schemas.synthese(
                len(payload.dossiers), len(scores), len(result.rejections), part_signalee
            ),
            "avertissement": schemas.AVERTISSEMENT,
        }
        if derive:
            body["derive"] = schemas.drift_to_dict(scoring.assess_drift(bundle, result.accepted))
        return body

    @app.post("/v1/predict-etudiant")
    def predict_etudiant(
        request: Request,
        dossier: dict[str, Any] = Body(...),
        seuil: float | None = Query(default=None),
        _: None = Depends(require_api_key),
        bundle: Bundle = Depends(require_ready),
    ) -> dict:
        service_local: ServiceSettings = request.app.state.settings
        threshold = _resolve_threshold(seuil, service_local, bundle.contract)
        result = validation.validate([dossier], bundle.contract.facts, bundle.contract.defaults)
        if result.rejections:
            raise HTTPException(
                status_code=422, detail=schemas.rejection_to_dict(result.rejections[0])
            )
        score = scoring.score(
            bundle,
            result.accepted,
            result.accepted_references,
            threshold=threshold,
            expose_indicator=service_local.exposer_indicateur,
        )[0]
        return {
            "seuil_applique": threshold,
            "provenance_seuil": _threshold_provenance(seuil, service_local),
            "resultat": schemas.score_to_dict(score),
            "avertissement": schemas.AVERTISSEMENT,
        }

    @app.get("/v1/modele")
    def modele(_: None = Depends(require_api_key), bundle: Bundle = Depends(require_ready)) -> dict:
        return schemas.fiche_to_dict(bundle.contract)

    @app.get("/v1/seuil")
    def seuil_en_vigueur(
        request: Request,
        _: None = Depends(require_api_key),
        bundle: Bundle = Depends(require_ready),
    ) -> dict:
        service_local: ServiceSettings = request.app.state.settings
        return {
            "seuil": _resolve_threshold(None, service_local, bundle.contract),
            "provenance": _threshold_provenance(None, service_local),
            "exposer_indicateur": service_local.exposer_indicateur,
        }

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready", response_model=None)
    def ready(request: Request) -> JSONResponse | dict:
        entrepot_local: EntrepotModele = request.app.state.entrepot
        if not entrepot_local.ready:
            return JSONResponse(
                status_code=503, content={"ready": False, "error": entrepot_local.error}
            )
        bundle = entrepot_local.bundle
        service_local: ServiceSettings = request.app.state.settings
        return {
            "ready": True,
            "version": bundle.contract.facts.version,
            "seuil": _resolve_threshold(None, service_local, bundle.contract),
            "n_variables": len(bundle.classifier.feature_names_in_),
        }

    if service.monitoring_actif:
        Instrumentator().instrument(app).expose(app, include_in_schema=False)

    return app


# Application par défaut, pour `uvicorn decrochage_l1.serving.api:app`. Charge l'artefact
# depuis `settings.models_dir` ; s'il manque, /ready répond 503 sans empêcher le démarrage.
app = create_app()
