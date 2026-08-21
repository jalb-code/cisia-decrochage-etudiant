# Jeux d'exemple — données synthétiques

Ces fichiers sont des **cohortes de démonstration synthétiques**, produites par un générateur (depuis
retiré du dépôt) pour exercer la CLI et le service d'inférence. Ils **ne contiennent aucune donnée
réelle d'étudiant** :

- **aucun identifiant direct ni indirect** (pas de nom, pas de `student_id`) — seule une référence de
  dossier **opaque** (`TEST-001`, `COH2026-0001`) ;
- **aucun attribut protégé** (ni `sexe`, ni `boursier`) — minimisation (art. 5.1.c du RGPD) ;
- uniquement les **champs d'entrée du modèle** (§10.3), tels qu'un SI scolarité les transmettrait.

Ils sont donc versionnables sans risque, contrairement aux jeux de `data/` (précaution RGPD, voir
[`data/README.md`](../../data/README.md)).

## Les trois jeux

| Fichier | Lignes | Cible | Usage |
|---|---|---|---|
| `cohorte_20_avec_erreurs.csv` | 20 | non | **`predict`** — écritures sales volontaires (« 67,2 % », « Assez bien », séparateur `;`) pour démontrer la conformation **puis la validation** (CLI) et le refus (API). |
| `cohorte_5000_sans_erreur.csv` | 5 000 | non | **`predict`** — campagne propre à l'échelle d'une promotion. |
| `cohorte_5000_derive.csv` | 5 000 | non | **`predict`** — distribution volontairement **dérivée**, pour illustrer la détection de dérive par campagne (§11.4, §13). |

## Ce qu'ils ne permettent pas

Aucun ne porte les cibles (`abandon`, `moyenne_finale`) : ce sont des jeux de **prédiction**, pas de
**ré-entraînement** (`retrain` exige des labels et assez de lignes pour le split et la validation
croisée). Voir la commande dans le [`README.md`](../../README.md) racine.
