"""Contrat d'entrée/sortie de l'API — schémas Pydantic typés.

L'entrée est **un modèle Pydantic à champs figés** (`PredictEtudiantForm`) : types, bornes et
modalités déclarés ici font foi, `extra="forbid"` refuse tout champ hors périmètre. C'est la
source de vérité du contrat d'entrée ; un test de non-écart garantit qu'il couvre exactement
les features du modèle. Les features **dérivées** (`taux_rendu`, `ratio_retards`) n'y figurent
pas : le service les calcule après validation (`normalization.add_derived`).

Sortie : probabilité d'`abandon`, note `moyenne_finale` bornée, contributions par thème, et
l'avertissement de l'article 22 (aide à la décision, décision humaine). La fiche (`ServiceContract`)
porte, elle, ce qu'un schéma d'entrée ne sait pas exprimer : seuil, dérive, thèmes, référence.
"""

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from decrochage_l1.serving.contract import ServiceContract
from decrochage_l1.serving.drift import CampaignDrift
from decrochage_l1.serving.explain import Contributions
from decrochage_l1.serving.scoring import DossierScore

# Mention systématique en sortie : matérialise l'absence de décision automatisée (art. 22).
AVERTISSEMENT = (
    "Aide à la décision : l'équipe pédagogique conserve la décision d'accompagnement. "
    "Aucun étudiant n'est contacté automatiquement. Les facteurs présentés sont des "
    "corrélations, pas des causes."
)

LOT_MAX = 10_000  # plafond d'un lot : un refus explicite plutôt qu'un épuisement mémoire

# Modalités canoniques (minuscule, sans accent) — miroir des modalités du modèle.
Filiere = Literal[
    "biologie",
    "droit",
    "gestion",
    "informatique",
    "lettres",
    "mathematiques",
    "psychologie",
    "staps",
]
BacType = Literal["general", "technologique", "professionnel"]
MentionBac = Literal["passable", "assez bien", "bien", "tres bien"]


class PredictEtudiantForm(BaseModel):
    """Relevé d'un étudiant à mi-S1 — le contrat d'entrée d'un scoring précoce.

    Champs requis = ceux sans manquant observé ; champs optionnels (déclaratifs, 4-8 % de
    manquants) laissés à `None`, imputés par le pipeline. Les cohérences inter-champs
    (`retards ≤ rendus ≤ total`) sont vérifiées ici, refus explicite sinon.
    """

    model_config = ConfigDict(extra="forbid")  # tout champ hors périmètre -> 422 nommant le champ

    reference_dossier: str | None = Field(
        None, description="Référence opaque du dossier, renvoyée telle quelle (jamais explicative)."
    )

    # --- Requis (0 % de manquants dans les données) ---
    age: int = Field(..., ge=16, le=99, examples=[19])
    filiere: Filiere = Field(..., examples=["informatique"])
    bac_type: BacType = Field(..., examples=["general"])
    taux_presence_pct: float = Field(..., ge=0, le=100, examples=[82.0])
    heures_lms_total: float = Field(..., ge=0, examples=[42.0])  # grandeur ouverte, sans plafond
    nb_ue_total: int = Field(..., ge=1, examples=[6])
    nb_devoirs_total: int = Field(..., ge=1, examples=[12])  # >= 1 : dénominateur des dérivées
    nb_devoirs_rendus: int = Field(..., ge=0, examples=[8])
    retards_rendus: int = Field(..., ge=0, examples=[1])
    messages_forum: int = Field(..., ge=0, examples=[3])

    # --- Optionnels (manquants 4-8 %) -> imputés par le pipeline ---
    mention_bac: MentionBac | None = Field(None, examples=["bien"])
    motivation: float | None = Field(None, ge=1, le=5, examples=[3.0])
    satisfaction: float | None = Field(None, ge=1, le=5, examples=[4.0])
    sentiment_appartenance: float | None = Field(None, ge=1, le=5, examples=[3.0])

    @model_validator(mode="after")
    def _coherences(self) -> "PredictEtudiantForm":
        """Refuse les incohérences inter-champs : retards ≤ rendus ≤ total."""
        if self.nb_devoirs_rendus > self.nb_devoirs_total:
            raise ValueError(
                f"nb_devoirs_rendus ({self.nb_devoirs_rendus}) > "
                f"nb_devoirs_total ({self.nb_devoirs_total})"
            )
        if self.retards_rendus > self.nb_devoirs_rendus:
            raise ValueError(
                f"retards_rendus ({self.retards_rendus}) > "
                f"nb_devoirs_rendus ({self.nb_devoirs_rendus})"
            )
        return self


# Colonnes d'entrée du modèle = champs du formulaire hors référence de dossier.
INPUT_FIELDS = tuple(f for f in PredictEtudiantForm.model_fields if f != "reference_dossier")


class PredictCohorteForm(BaseModel):
    """Un lot de dossiers. `list[dict]` **délibérément** : chaque ligne est validée séparément
    contre `PredictEtudiantForm`, une ligne invalide ne fait pas échouer la requête entière.
    """

    dossiers: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=LOT_MAX,
        description="Lot de dossiers ; chaque élément suit PredictEtudiantForm, "
        "validé ligne à ligne (refus partiel).",
        json_schema_extra={"items": {"$ref": "#/components/schemas/PredictEtudiantForm"}},
    )


class ContributionTheme(BaseModel):
    """Contribution agrégée d'un thème à la log-cote (signée : protège < 0 < aggrave)."""

    theme: str
    contribution: float


class ContributionVariable(BaseModel):
    """Contribution d'une variable à la log-cote (signée : protège < 0 < aggrave)."""

    variable: str
    contribution: float


class PredictEtudiantReponse(BaseModel):
    """Résultat d'un dossier : probabilité, note estimée, indicateur et explicabilité."""

    reference_dossier: str | None
    proba_abandon: float = Field(..., ge=0, le=1)
    moyenne_finale: float = Field(..., ge=0, le=20)
    signaled: bool | None  # None quand l'indicateur n'est pas exposé (probabilité seule)
    seuil_applique: float | None  # None hors régime indicateur : le seuil ne gouverne rien
    provenance_seuil: str | None
    version_modele: str
    contributions_theme: list[ContributionTheme]
    contributions_variable: list[ContributionVariable]  # détail dépliable sous les thèmes
    avertissement: str = AVERTISSEMENT


class DossierRefuse(BaseModel):
    """Une ligne refusée : son rang (base 0), sa référence si lisible, et ses motifs."""

    index: int
    reference_dossier: str | None
    erreurs: list[dict]  # {champ, message}, tel que produit par la validation Pydantic


class SyntheseCohorte(BaseModel):
    """Synthèse d'une campagne : reçus, scorés, refusés, et part signalée si exposée."""

    dossiers_recus: int
    dossiers_scores: int
    dossiers_refuses: int
    part_signalee: float | None


class PredictCohorteReponse(BaseModel):
    """Réponse d'une campagne : résultats dans l'ordre reçu, refus, synthèse, dérive optionnelle."""

    seuil_applique: float | None  # None hors régime indicateur : le seuil ne gouverne rien
    provenance_seuil: str | None
    resultats: list[PredictEtudiantReponse]
    refuses: list[DossierRefuse]
    synthese: SyntheseCohorte
    avertissement: str = AVERTISSEMENT
    derive: dict | None = None


def _clean(value: Any) -> Any:
    """Ramène un flottant `NaN` à `null` : le JSON ne représente pas NaN."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _themes(contributions: Contributions) -> list[ContributionTheme]:
    """Contributions par thème, triées par amplitude décroissante."""
    ordered = sorted(contributions.by_theme.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return [ContributionTheme(theme=t, contribution=v) for t, v in ordered]


def _variables(contributions: Contributions, top: int | None) -> list[ContributionVariable]:
    """Contributions par variable, triées par amplitude ; `top` limite aux plus fortes (lot)."""
    ordered = sorted(contributions.by_variable.items(), key=lambda kv: abs(kv[1]), reverse=True)
    if top is not None:
        ordered = ordered[:top]
    return [ContributionVariable(variable=v, contribution=c) for v, c in ordered]


def etudiant_reponse(
    score: DossierScore,
    *,
    seuil: float | None,
    provenance: str | None,
    version: str,
    top: int | None = None,
) -> PredictEtudiantReponse:
    """Assemble la réponse d'un dossier ; `top` borne le détail par variable (vue campagne)."""
    return PredictEtudiantReponse(
        reference_dossier=score.reference,
        proba_abandon=score.probability,
        moyenne_finale=score.moyenne_finale,
        signaled=score.signaled,
        seuil_applique=seuil,
        provenance_seuil=provenance,
        version_modele=version,
        contributions_theme=_themes(score.contributions),
        contributions_variable=_variables(score.contributions, top),
    )


def drift_to_dict(drift_result: CampaignDrift) -> dict:
    """Bilan de dérive en JSON, valeurs `NaN` ramenées à `null`."""
    return {
        "mesurable": drift_result.mesurable,
        "motif": drift_result.motif,
        "verdict": drift_result.verdict,
        "psi_max": _clean(drift_result.psi_max),
        "variables": [
            {
                "variable": v.variable,
                "psi": _clean(v.psi),
                "ks_statistic": _clean(v.ks_statistic),
                "ks_pvalue": _clean(v.ks_pvalue),
                "shift_std": _clean(v.shift_std),
                "verdict": v.verdict,
            }
            for v in drift_result.variables
        ],
    }


def fiche_to_dict(contract: ServiceContract) -> dict:
    """La fiche publiée par `/v1/modele` : descripteur de service (le contrat d'entrée, lui,
    est publié par l'OpenAPI du schéma `PredictEtudiantForm`).
    """
    facts, defaults = contract.facts, contract.defaults
    return {
        "version": facts.version,
        "numeric": list(facts.numeric),
        "categorical": list(facts.categorical),
        "themes": dict(facts.themes),
        "seuil_defaut": defaults.threshold,
        "derive": {
            "surveillance": defaults.drift_surveillance,
            "alerte": defaults.drift_alerte,
            "effectif_min": defaults.drift_effectif_min,
        },
    }
