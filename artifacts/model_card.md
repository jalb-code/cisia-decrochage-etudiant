# Model card — Détection du décrochage en L1 (mi-S1)

**Version** 1.0.0 · **Date** 2026-08-21 · **Responsable de traitement** Établissement

## Détails du modèle

Modèle d'aide à la décision qui estime, à mi-parcours du premier semestre, la probabilité qu'un étudiant de L1 abandonne, afin de déclencher un accompagnement humain.

- **Développé par** — Julien ALBURQUERQUE
- **Type** — deux modèles - classification (régression logistique, probabilités nativement fiables et non recalibrées, D31) pour la probabilité d'abandon ; régression (gradient boosting) pour une estimation de la note finale, secondaire, qui hiérarchise l'intensité de l'accompagnement
- **Cibles** — abandon (probabilité, principale) · moyenne_finale (/20, secondaire)
- **Langue des données** — français
- **Licence** — usage uniquement dans le cadre de la certification CISIA

## Usages

**Usage direct.** Prioriser l'accompagnement des étudiants de L1 à mi-S1. La sortie principale est une probabilité, jamais une classe ni une décision.

**Utilisateurs visés.** Cellule pédagogique et tuteurs de l'établissement.

**Hors périmètre.** Aucune décision administrative automatisée (orientation, sanction, sélection). Aide à la décision : la décision d'accompagnement reste humaine (RGPD, art. 22). Ne jamais exposer la seule classe binaire à l'utilisateur.

## Biais, risques et limites

- Cohorte d'un seul établissement et d'une seule année : généralisation à valider ailleurs.
- Seuil fixé sur l'OOF et non recalé sur le test (par principe) : le rappel y est au niveau du plancher visé.
- Petits sous-groupes non concluants ; modalité établissement « autre » à surveiller en exploitation.
- Aucune variable protégée ni proxy socio-économique en entrée (minimisation).
- Garde-fous contre la stigmatisation et la prophétie auto-réalisatrice à tenir côté usage.

**Recommandations.**

- Conserver la décision d'accompagnement humaine ; ne jamais exposer la seule classe binaire.
- Rappeler l'avertissement de l'article 22 dans la documentation et l'outil
- Suivre la dérive des entrées par campagne et demander un ré-entraînement quand elle se confirme.

## Données d'entraînement

Cohorte L1, jeu « gold » nettoyé et validé : 4160 étudiants au train, 28.4% d'abandons. Variables connues à mi-S1 uniquement, sans fuite temporelle. Attributs protégés (sexe, boursier) exclus du modèle, conservés hors modèle pour l'audit d'équité.

## Évaluation

Test scellé (20 % du jeu, jamais vu à l'entraînement), une seule passe. Seuil et hyperparamètres figés sur le train ; probabilités non recalibrées (D31).

**Métriques sur le test scellé.**

| Métrique | Valeur |
|---|---|
| PR-AUC (abandon) | 0.872 |
| ROC-AUC (abandon) | 0.945 |
| Rappel @seuil 0.42 | 79% |
| Précision @seuil 0.42 | 77% |
| Brier (fiabilité des probabilités) | 0.0849 |
| MAE note finale | 2.24 pts/20 |

**Seuil de décision.** 0.42, fixé sur un plancher de rappel (le coût d'un décrocheur manqué dépasse celui d'une fausse alerte) ; paramètre d'exploitation, jamais figé dans les poids.

**Équité.** Rappel comparable entre sexes et statuts boursiers : pas de décrocheur davantage manqué selon le sexe ou la précarité.

## Spécifications techniques

Pipeline scikit-learn (préprocesseur + estimateur) sérialisé (joblib), servi par une API FastAPI. L'entrée est typée et validée ; le service ne journalise aucune donnée en exploitation. Seul un instantané du train (sans identifiant ni attribut protégé) est scellé dans l'artefact pour mesurer la dérive, remplacé à chaque ré-entraînement.

## Contact

Julien ALBURQUERQUE (responsable du projet).
