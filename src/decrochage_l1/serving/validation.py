"""Validation d'un dossier contre la fiche — refus explicites, ligne à ligne, jamais muets.

Trois familles de contrôles, dans l'ordre où ils se lisent :

- **Structurel** — un champ hors périmètre (`moyenne_partiels_s1`) ou une variable dérivée
  transmise par l'appelant sont **refusés en nommant le champ**. C'est la preuve exécutable
  du refus de fuite : rien n'est scoré en silence.
- **Bornes** — refus explicite d'une valeur hors domaine, jamais d'écrêtage.
- **Cohérences** et **modalités** — les inégalités inter-champs de la fiche, et le refus
  d'une modalité catégorielle inconnue.

Une valeur **manquante** n'est pas une erreur : une cellule vide est une absence, imputée
plus loin par le pipeline. Sur un lot, **une ligne invalide n'en bloque aucune autre** : elle
est refusée avec son index et son motif, les autres sont conformées et retenues.

Les seuils, bornes et cohérences viennent de la fiche (`defaults`), **passés**, jamais codés.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import pandas as pd

from decrochage_l1.serving import normalization
from decrochage_l1.serving.contract import ModelFacts, OperationalDefaults

# Référence opaque du dossier : métadonnée acceptée hors périmètre de scoring, renvoyée
# telle quelle, jamais une variable explicative. Réglable par l'appelant de `validate`.
REFERENCE_FIELD = "reference_dossier"


@dataclass(frozen=True)
class FieldError:
    """Un motif de refus, rattaché au champ en cause — jamais un message anonyme."""

    field: str
    message: str


@dataclass(frozen=True)
class RowRejection:
    """Une ligne refusée : son rang (base 0), sa référence si lisible, et ses motifs."""

    index: int
    reference: str | None
    errors: tuple[FieldError, ...]


@dataclass
class ValidationResult:
    """Issue d'une validation de lot : les lignes retenues (conformées) et les refus."""

    accepted: pd.DataFrame  # conformées + dérivées ; index positionnel d'origine conservé
    accepted_references: list[str | None]  # référence de chaque ligne retenue, alignée
    rejections: tuple[RowRejection, ...]


def _structural_errors(
    keys: Iterable[str], facts: ModelFacts, reference_field: str
) -> list[FieldError]:
    """Refuse un champ hors périmètre ou une variable dérivée transmise par l'appelant."""
    allowed = set(facts.input_columns) | {reference_field}
    derived = set(facts.derived_columns)
    errors: list[FieldError] = []
    for key in keys:
        if key in derived:
            errors.append(
                FieldError(key, "variable dérivée, calculée par le service — à ne pas transmettre")
            )
        elif key not in allowed:
            errors.append(FieldError(key, "champ hors périmètre du modèle"))
    return errors


def _bounds_errors(row: Mapping, defaults: OperationalDefaults) -> list[FieldError]:
    """Refuse une valeur hors bornes ; un manquant n'est pas contrôlé (absence légitime)."""
    errors: list[FieldError] = []
    for field_name, bound in defaults.bounds.items():
        value = row.get(field_name)
        if pd.isna(value):
            continue
        if not bound.contains(value):
            errors.append(
                FieldError(field_name, f"hors bornes [{bound.minimum} ; {bound.maximum}]")
            )
    return errors


def _coherence_errors(row: Mapping, defaults: OperationalDefaults) -> list[FieldError]:
    """Refuse une incohérence inter-champs ; un champ manquant ne l'infirme pas."""
    errors: list[FieldError] = []
    for rule in defaults.coherence:
        if pd.isna(row.get(rule.left)) or pd.isna(row.get(rule.right)):
            continue
        if not rule.holds(row):
            errors.append(FieldError(rule.left, f"{rule.left} > {rule.right}"))
    return errors


def _modality_errors(row: Mapping, facts: ModelFacts) -> list[FieldError]:
    """Refuse une modalité catégorielle inconnue ; un manquant est laissé au pipeline."""
    errors: list[FieldError] = []
    for column, modalities in facts.nominal_modalities.items():
        value = row.get(column)
        if pd.isna(value):
            continue
        if value not in modalities:
            admises = ", ".join(modalities)
            errors.append(
                FieldError(column, f"modalité inconnue : {value!r} (admises : {admises})")
            )
    return errors


def validate(
    raw_rows: list[Mapping],
    facts: ModelFacts,
    defaults: OperationalDefaults,
    *,
    reference_field: str = REFERENCE_FIELD,
) -> ValidationResult:
    """Valide un lot de dossiers bruts, conforme les lignes retenues, motive les refus.

    Le contrôle structurel porte sur les clés **brutes** de chaque ligne (avant toute
    conversion) ; les contrôles de valeur portent sur la ligne **conformée**. Le lot est
    conformé en une passe (vectorisé), colonnes d'entrée manquantes ramenées à des absences.
    """
    references: list[str | None] = [row.get(reference_field) for row in raw_rows]
    structural: list[list[FieldError]] = [
        _structural_errors(row.keys(), facts, reference_field) for row in raw_rows
    ]

    # Toutes les colonnes d'entrée existent (absentes -> NA) pour que la conformation et les
    # dérivées ne butent pas sur une colonne manquante d'un lot partiel.
    columns = sorted({key for row in raw_rows for key in row} | set(facts.input_columns))
    frame = pd.DataFrame(list(raw_rows), columns=columns)
    conformed = normalization.add_derived(normalization.conform_frame(frame, facts))

    rejections: list[RowRejection] = []
    accepted_positions: list[int] = []
    for i in range(len(raw_rows)):
        row_values = conformed.iloc[i].to_dict()
        errors = [
            *structural[i],
            *_bounds_errors(row_values, defaults),
            *_coherence_errors(row_values, defaults),
            *_modality_errors(row_values, facts),
        ]
        if errors:
            rejections.append(RowRejection(index=i, reference=references[i], errors=tuple(errors)))
        else:
            accepted_positions.append(i)

    return ValidationResult(
        accepted=conformed.iloc[accepted_positions].reset_index(drop=True),
        accepted_references=[references[i] for i in accepted_positions],
        rejections=tuple(rejections),
    )
