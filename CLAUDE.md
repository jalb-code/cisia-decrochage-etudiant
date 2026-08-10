# CLAUDE.md — decrochage-l1

Règles de travail sur ce dépôt. Arborescence et démarrage : [README.md](README.md).
(Préférences personnelles globales dans `~/.claude/CLAUDE.md`.)

## Objet et livrable

Certification IA (référentiel **C1 → C9**). Détecter **à mi-parcours du S1** les étudiants de L1 à
risque de décrochage, pour déclencher un accompagnement. Deux cibles : **`abandon`** (0/1,
classification, principale) et **`moyenne_finale`** (/20, régression, secondaire).

**Le livrable est un notebook unique** — `notebooks/JALB-Decrochage-l1.ipynb` — exécutable et
**lisible sans explication orale**, structuré selon le plan imposé de 16 sections (0 à 15).
Y sont joints : les jeux de données utilisés, le support de soutenance, les scripts utilitaires.

## Les trois règles

**1. Une décision s'écrit une seule fois, dans le journal de bord de sa section.**
Le *journal de bord* est ce que l'énoncé exige — les décisions justifiées, en fin de section, dans
le notebook. Il compte pour moitié dans l'écrit noté. Pas de fiche séparée qui redit la même chose
ailleurs. Gabarit, cinq lignes :

> **Question** — … · **Ce que j'ai regardé** — … · **Écarté** — X, parce que Y · **Décidé** — Z,
> parce que (article, mesure ou contrainte).

La ligne **Écarté** est obligatoire : c'est elle qui répond aux 30 minutes de questions du jury.

**2. Une décision empirique ne s'écrit pas avant la mesure qui la fonde.**
Deux familles, deux régimes :

| | Quand ça s'écrit |
|---|---|
| **Empirique** — leurres, manquants, features, exclusions, seuil, modèle | **après** la mesure |
| **Cadrage / conformité** — base légale, art. 22, minimisation, responsabilités, alternatives | quand on rédige la section ; aucun résultat ne les produira |

**3. `docs/local/` ne fait pas autorité.**
Notes, brouillons et matière du projet précédent (`docs/local/reserve/`) sont **à challenger**,
jamais à citer ni à recopier. Un fait n'entre dans le notebook qu'après **re-mesure** ; une décision
qu'après **ré-instruction** ; l'un et l'autre après **feu vert de Julien**. Aucun fichier versionné
ne cite un fichier de cette zone (garde `no-local-file-refs`).

## Le registre des questions/décisions

`docs/registre-decisions.csv` — **vue de navigation, il ne remplace rien**. Le notebook porte les
décisions justifiées pour l'auditeur qui le lit linéairement ; le registre dit seulement **où une
question est posée et où elle est tranchée**, pour qu'aucune ne reste en l'air.

`id, question, posee_en, tranchee_en, decision, perimetre, statut`

- **Il ne porte jamais l'argumentation.** Le *pourquoi* vit dans le journal de bord et nulle part
  ailleurs. `decision` tient en une clause.
- `perimetre` vaut `minimal` (exigé par l'énoncé) ou `optimal` (différenciant) — **réarbitrable à
  tout moment** ; le déplacement d'une ligne est lui-même une décision, justifiée au journal.
- Une ligne à `tranchee_en` vide est une question ouverte. Aucune ne doit rester vide à la fin.
- Son intégration en annexe du notebook ou du support : **décision différée**.

## Le notebook, lisible par un jury

1. **Un fait = une sortie de cellule.** Le markdown commente, il ne recalcule pas.
2. **Sous chaque sortie, un bilan court** : titre gras portant le chiffre clé, 3-4 puces, une
   phrase de chute qui dit ce que ça implique — sans décider.
3. **En fin de section, le journal de bord.** Rien d'autre.
4. **Zéro lien sortant.** Le notebook est autoportant. Le matériel long va en **§15 Annexes**.
5. **Une cellule markdown ≤ 1 écran.** Si ça déborde, il y a deux idées dedans.
6. **Un sujet, un endroit.** Une section *cadre* (le pourquoi) ou *réalise* (le comment), jamais
   les deux ; celle qui réalise renvoie à celle qui a cadré.
7. **Le markdown ne promet jamais ce que le code ne fait pas.** Toute affirmation est adossée à une
   sortie affichée, ou reformulée en intention explicite (« je n'ai pas fait X, parce que… »).

## Découpage des sections données (C3)

Un **palier est un état de la donnée, pas une unité de rédaction**.

| § | Rôle | Produit |
|---|---|---|
| **5** Chargement et compréhension | profiler, constater, inventorier les modalités | **bronze** — conformation d'écriture, recodage, dédoublonnage. N'arbitre rien, ne perd aucune information |
| **6** EDA | mesurer, interpréter, **décider** — sur l'ensemble du jeu | rien : aucune donnée n'est modifiée |
| **7** Préparation | appliquer les décisions de §6 | **silver** → **gold**. La section se clôt sur le jeu de référence et ses décisions |
| **9** Entraînement | **splitter**, puis ajuster le `Pipeline` sur le train seul | partition train / test, puis imputation, encodages, scaling |

**Le gold est le jeu de référence : propre, annoté, validé, lisible par un humain.** Ce n'est pas la
matrice que consomme `fit()` — celle-là est la sortie du `Pipeline`, et n'est pas un palier.
Critère d'appartenance : *si une colonne du gold n'est plus lisible telle quelle dans un tableur,
elle appartient au `Pipeline`*. `assez bien` reste `assez bien` ; un `1` à sa place, ou six colonnes
`mention_bac_*`, relèvent du `Pipeline`.

| Dans le gold (déterministe) | Dans le `Pipeline` (apprend, donc après le split) |
|---|---|
| exclusions de principe, jointure catalogue, dérivations ligne à ligne (`taux_rendu`) | imputation, one-hot, encodage ordinal, scaling |

**L'exploration porte sur l'ensemble du jeu** — décrire les données, c'est les décrire toutes, et
c'est ce qui garantit qu'aucune modalité rare ne manque à l'inventaire. Deux garde-fous :

- **Le vocabulaire catégoriel est déclaré, jamais déduit** — `schema.CANONICAL_MODALITIES` fait foi,
  et l'encodeur le reçoit explicitement (`categories=[...]`, `handle_unknown="ignore"`). Une
  modalité absente du train ne peut pas faire disparaître sa colonne.
- **Aucune inclusion ni exclusion ne se décide sur une relation mesurée avec la cible.** Les
  exclusions sont *de principe* (fuite temporelle, identifiants, variance nulle, minimisation).
  Corollaire : **les leurres ne sont pas retirés** — ils traversent le gold, entrent dans le modèle,
  et §12 montre que SHAP leur donne un poids ≈ 0. Les démontrer nuls vaut mieux que les croire.

**Le split ouvre §9 et scelle le test** : ni ajustement, ni hyperparamètre, ni seuil, ni sélection de
modèle ne le regardent avant §12. Sa place est là, et non en §7, parce que la partition n'est pas un
état de la donnée mais le **protocole d'évaluation** — l'attendu C5, « stratégie
train/validation/test sans fuite ». Tout ce qui concerne la **validation** — validation croisée ou
jeu de validation découpé dans le train, calibration sur prédictions *out-of-fold* ou sur une
tranche dédiée — se décide dans la même section, **à l'intérieur du train**.

## Sources de vérité

| Domaine | Source |
|---|---|
| Stack (Python, dépendances, versions) | `pyproject.toml` — `uv.lock` en est la résolution, générée |
| Chemins d'exécution | `config.py`, surchargeable par `DECROCHAGE_L1_*` |
| Faits sur les données | la **mesure**, consignée en sortie de cellule du notebook |
| Décisions et leur *pourquoi* | le **journal de bord** du notebook |
| Où une question se pose / se tranche | `docs/registre-decisions.csv` |
| Exigences C1→C9 | l'énoncé (`docs/cas_usage/`), puis ce fichier |

En cas de contradiction : l'énoncé l'emporte ; pour la stack, `pyproject.toml` ; pour un chiffre,
la mesure sur les données.

## Agents

Trois relecteurs, **lecture seule**, à invoquer en fin de section — jamais pour décider :
`consultant-ml` (méthode, fuite, métriques, protocole), `consultant-rgpd` (RGPD, éthique, biais),
`gardien-cas-usage` (couverture C1→C9, périmètre des sections, défendabilité).

## Conventions de code

**Langue.** Code en **anglais** (verbes, fonctions, variables) ; **docstrings et commentaires en
français**. Seul le **vocabulaire métier** reste français, parce qu'il calque les données : noms de
colonnes (`abandon`, `moyenne_finale`, `filiere`…) et entités (`etudiants`, `catalogue`), jusqu'au
package `decrochage_l1`. D'où un franglais assumé : `load_etudiants`, `parse_number`.

**Nommage.** `snake_case` (variables / fonctions), `PascalCase` (classes), `UPPER_SNAKE_CASE`
(constantes).

**Documentation = docstrings** (vérifiées par ruff `D100`–`D103`) : une par module (ce qu'il fait,
ce qu'il ne fait pas), une par fonction publique (rôle, et le *pourquoi* quand il n'est pas
évident). Les commentaires `#` sont réservés au non-évident — jamais une paraphrase du code, jamais
de code mort commenté.

**Philosophie.** La logique réutilisable vit dans `src/decrochage_l1/`, testée ; le notebook
l'appelle. Les données préparées sont **produites par le code**, jamais à la main. Clair avant
malin ; type hints partout ; pandas vectorisé. `random_state` fixés.

## Avant commit

Un commit ne se fait **que sur demande explicite de Julien**. Le feu vert donné :

1. **Documentation à jour** — `README.md`, `CLAUDE.md` reflètent l'état réel du code.
2. **Aucune référence morte**, aucun fichier versionné citant `docs/local/<fichier>`.
3. **Revue du `git diff --staged`** — pas de `print` de debug, pas de code mort, et aucune ressource
   non versionnée stagée (`data/`, `models/`, `reports/`, `docs/local/`, `*.local.ipynb`).
4. **Message conventionnel** (`feat` / `fix` / `docs` / `refactor`), **commit atomique**.
