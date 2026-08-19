"""Service d'inférence (§11) — FastAPI, deux routes de prédiction et les sondes.

Cinq principes tenus par le code :

- **la sortie principale est une probabilité**, pas une classe ; l'indicateur « signalé »
  n'apparaît que si l'exploitation l'expose, et le seuil est un **paramètre** (fiche, ou
  surcharge d'environnement, ou `?seuil=` d'un appel), jamais dans les poids ;
- **le service ne conserve rien** — aucune écriture, aucune base ;
- **l'entrée est typée** — `PredictEtudiantForm` valide types, bornes, modalités et cohérences ;
  un champ hors périmètre est refusé en le nommant (`extra="forbid"`) ;
- **`/health` dit si le processus vit, `/ready` si le modèle est utilisable** — deux sondes ;
- **le modèle est chargé une fois**, au démarrage, via l'entrepôt injecté.

Chaque réponse porte l'avertissement de l'article 22 : aide à la décision, la décision reste
humaine. La route `/v1/predict-cohorte` est la principale (le régime réel est une campagne),
validée **ligne à ligne** (une ligne invalide est refusée seule) ; `/v1/predict-etudiant` sert
le test ponctuel d'un dossier.
"""

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import ValidationError

from decrochage_l1.config import settings as runtime_settings
from decrochage_l1.serving import metrics, normalization, schemas, scoring
from decrochage_l1.serving.contract import ServiceContract
from decrochage_l1.serving.settings import ServiceSettings
from decrochage_l1.serving.store import Bundle, EntrepotModele

TOP_CONTRIBUTIONS_CAMPAGNE = 6  # une campagne n'expose que les facteurs principaux par ligne


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


def _resolve_drift(service: ServiceSettings, contract: ServiceContract) -> tuple[float, float, int]:
    """Bornes de dérive effectives : la configuration prime, sinon le défaut de la fiche.

    Chaque borne se surcharge indépendamment ; l'ordre surveillance <= alerte et effectif_min > 0
    sont revérifiés ici, car une surcharge d'exploitation pourrait les rompre.
    """
    defaults = contract.defaults
    surveillance = (
        service.drift_surveillance
        if service.drift_surveillance is not None
        else defaults.drift_surveillance
    )
    alerte = service.drift_alerte if service.drift_alerte is not None else defaults.drift_alerte
    effectif_min = (
        service.drift_effectif_min
        if service.drift_effectif_min is not None
        else defaults.drift_effectif_min
    )
    if not 0.0 <= surveillance <= alerte:
        raise HTTPException(
            status_code=422,
            detail=f"seuils de dérive non ordonnés : surveillance={surveillance}, alerte={alerte}",
        )
    if effectif_min <= 0:
        raise HTTPException(
            status_code=422, detail=f"effectif minimal non positif : {effectif_min}"
        )
    return surveillance, alerte, effectif_min


def _frame_entree(forms: list[schemas.PredictEtudiantForm]) -> pd.DataFrame:
    """DataFrame des colonnes d'entrée du modèle (hors référence), dérivées ajoutées ensuite."""
    lignes = [f.model_dump(exclude={"reference_dossier"}) for f in forms]
    return normalization.add_derived(pd.DataFrame(lignes, columns=list(schemas.INPUT_FIELDS)))


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

    # État initial des métriques métier : disponibilité, séries de refus à zéro, et le seuil de
    # décision configuré. La jauge de seuil reflète la politique en place (fiche ou surcharge),
    # indépendamment du régime : la surveillance d'exploitation la lit même sans indicateur exposé
    # - c'est aux réponses, vues par l'utilisateur, de taire le seuil hors régime, pas au pilotage.
    metrics.set_model_loaded(entrepot.ready)
    metrics.init_refus_series(schemas.INPUT_FIELDS)
    if entrepot.ready:
        metrics.set_threshold(_resolve_threshold(None, service, entrepot.bundle.contract))

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

    @app.post("/v1/predict-cohorte", response_model=schemas.PredictCohorteReponse)
    def predict_cohorte(
        request: Request,
        payload: schemas.PredictCohorteForm,
        seuil: float | None = Query(default=None),
        capacite: int | None = Query(default=None, ge=1),
        derive: bool = Query(default=False),
        _: None = Depends(require_api_key),
        bundle: Bundle = Depends(require_ready),
    ) -> schemas.PredictCohorteReponse:
        service_local: ServiceSettings = request.app.state.settings
        expose = service_local.exposer_indicateur

        # Seuil et capacité ne gouvernent que l'indicateur : hors régime « avec indicateur », ils
        # ne produisent aucune sortie -> refus explicite plutôt qu'effet silencieux. Ils fixent la
        # même chose (le point de coupe) de deux façons, donc exclusifs.
        if not expose and (seuil is not None or capacite is not None):
            raise HTTPException(
                status_code=422, detail="seuil et capacite requièrent l'exposition de l'indicateur"
            )
        if seuil is not None and capacite is not None:
            raise HTTPException(status_code=422, detail="seuil et capacite sont exclusifs")

        # Validation ligne à ligne : une ligne invalide est refusée seule, motif à l'appui, et
        # chaque colonne mise en cause incrémente le compteur de refus de périmètre.
        forms: list[schemas.PredictEtudiantForm] = []
        positions: list[int] = []
        refuses: list[schemas.DossierRefuse] = []
        for i, brut in enumerate(payload.dossiers):
            try:
                forms.append(schemas.PredictEtudiantForm.model_validate(brut))
                positions.append(i)
            except ValidationError as erreur:
                erreurs: list[dict] = []
                for e in erreur.errors():
                    colonne = ".".join(str(x) for x in e["loc"]) or "_modele"
                    metrics.increment_refus(colonne)
                    erreurs.append({"champ": colonne, "message": e["msg"]})
                refuses.append(
                    schemas.DossierRefuse(
                        index=i, reference_dossier=brut.get("reference_dossier"), erreurs=erreurs
                    )
                )

        frame = _frame_entree(forms) if forms else pd.DataFrame()

        # Politique de décision, résolue seulement en régime indicateur : par capacité (coupe
        # relative à la cohorte) ou par seuil (appel > configuration > fiche).
        threshold: float | None = None
        provenance: str | None = None
        if expose:
            if capacite is not None:
                threshold = scoring.capacity_threshold(bundle, frame, capacite)
                provenance = "capacite"
            else:
                threshold = _resolve_threshold(seuil, service_local, bundle.contract)
                provenance = _threshold_provenance(seuil, service_local)

        resultats: list[schemas.PredictEtudiantReponse] = []
        if forms:
            scores = scoring.score(
                bundle,
                frame,
                [f.reference_dossier for f in forms],
                threshold=threshold,
                expose_indicator=expose,
            )
            resultats = [
                schemas.etudiant_reponse(
                    s,
                    seuil=threshold,
                    provenance=provenance,
                    version=bundle.contract.facts.version,
                    top=TOP_CONTRIBUTIONS_CAMPAGNE,
                )
                for s in scores
            ]

        part_signalee = None
        if expose and resultats:
            part_signalee = sum(1 for r in resultats if r.signaled) / len(resultats)

        reponse = schemas.PredictCohorteReponse(
            seuil_applique=threshold,
            provenance_seuil=provenance,
            resultats=resultats,
            refuses=refuses,
            synthese=schemas.SyntheseCohorte(
                dossiers_recus=len(payload.dossiers),
                dossiers_scores=len(resultats),
                dossiers_refuses=len(refuses),
                part_signalee=part_signalee,
            ),
        )
        if derive and forms:
            surveillance, alerte, effectif_min = _resolve_drift(service_local, bundle.contract)
            reponse.derive = schemas.drift_to_dict(
                scoring.assess_drift(
                    bundle,
                    frame,
                    seuil_surveillance=surveillance,
                    seuil_alerte=alerte,
                    effectif_min=effectif_min,
                )
            )
        return reponse

    @app.post("/v1/predict-etudiant", response_model=schemas.PredictEtudiantReponse)
    def predict_etudiant(
        request: Request,
        form: schemas.PredictEtudiantForm,
        seuil: float | None = Query(default=None),
        _: None = Depends(require_api_key),
        bundle: Bundle = Depends(require_ready),
    ) -> schemas.PredictEtudiantReponse:
        service_local: ServiceSettings = request.app.state.settings
        expose = service_local.exposer_indicateur
        if not expose and seuil is not None:
            raise HTTPException(
                status_code=422, detail="seuil requiert l'exposition de l'indicateur"
            )
        threshold: float | None = None
        provenance: str | None = None
        if expose:
            threshold = _resolve_threshold(seuil, service_local, bundle.contract)
            provenance = _threshold_provenance(seuil, service_local)
        score = scoring.score(
            bundle,
            _frame_entree([form]),
            [form.reference_dossier],
            threshold=threshold,
            expose_indicator=expose,
        )[0]
        return schemas.etudiant_reponse(
            score,
            seuil=threshold,
            provenance=provenance,
            version=bundle.contract.facts.version,
        )

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
        expose = service_local.exposer_indicateur
        return {
            # Hors régime indicateur, aucun seuil n'est en vigueur : politique « proba seule ».
            "seuil": _resolve_threshold(None, service_local, bundle.contract) if expose else None,
            "provenance": _threshold_provenance(None, service_local) if expose else None,
            "exposer_indicateur": expose,
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
        expose = service_local.exposer_indicateur
        return {
            "ready": True,
            "version": bundle.contract.facts.version,
            "exposer_indicateur": expose,
            # Le seuil n'accompagne la sonde que lorsqu'il gouverne l'indicateur.
            "seuil": _resolve_threshold(None, service_local, bundle.contract) if expose else None,
            "n_variables": len(bundle.classifier.feature_names_in_),
        }

    if service.monitoring_actif:
        Instrumentator().instrument(app).expose(app, include_in_schema=False)

    return app


# Application par défaut, pour `uvicorn decrochage_l1.serving.api:app`. Charge l'artefact
# depuis `settings.models_dir` ; s'il manque, /ready répond 503 sans empêcher le démarrage.
app = create_app()
