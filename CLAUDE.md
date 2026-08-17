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
Le *journal de bord* est ce que l'énoncé exige — « chaque décision doit pouvoir être **expliquée et
défendue à l'oral** » — les décisions justifiées, en fin de section, dans le notebook. Il compte
pour moitié dans l'écrit noté. Pas de fiche séparée qui redit la même chose ailleurs. Gabarit :

> **Question** — … · **Ce que j'ai regardé** — … · **Décision** — Z · **Pourquoi** — parce que
> (article, mesure ou contrainte).

Quand un choix alternatif crédible a été pesé, une ligne **Écarté — X, parce que Y** l'explicite :
l'énoncé ne l'exige pas, mais c'est elle qui alimente les 30 minutes de questions du jury et sert la
consigne « démarquez-vous par la rigueur ». On **nomme l'alternative sérieuse**, on ne dresse pas
l'inventaire de toutes les options ; on l'omet quand la décision n'a pas d'alternative défendable.

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

### Les invariants

1. **Un fait = une sortie de cellule.** Le markdown commente, il ne recalcule pas, et ne cite aucun
   chiffre qu'une sortie n'affiche pas. Toute affirmation est adossée à une sortie, ou reformulée
   en intention explicite (« je n'ai pas fait X, parce que… »).
2. **Zéro lien sortant** — pas un `](../…)` tapé à la main. Un chemin n'apparaît que **produit par
   le code** depuis `settings`. Le matériel long va en **§15 Annexes**.
3. **Le notebook ne fait pas de cours.** Il montre le résultat d'une méthode, il ne l'enseigne pas.
   Un argument de méthode ne s'écrit que si le jury peut le contester.
4. **Le silence est une forme.** Une sortie qui n'appelle ni décision, ni contrôle, ni report se
   passe de commentaire — on ne glose pas pour meubler.
5. **Ce qui reste ouvert s'écrit à l'endroit de la mesure qui l'a levé**, pas dans une table
   « Décisions » / « À décider » séparée. Un **bilan factuel** de l'état de la donnée (types,
   manquants, modalités) reste permis : il constate un état, il ne rejoue aucune décision.
6. **Un sujet, un endroit.** Une section *cadre* (le pourquoi) ou *réalise* (le comment), jamais
   les deux ; celle qui réalise renvoie à celle qui a cadré, par un `§N` nu.
7. **N'affiche rien que le lecteur puisse lire ailleurs.** Ce qu'une sortie déjà à l'écran contient,
   ou ce qu'un rapport annexe détaille, se **rapporte en puces** — on n'ajoute pas de sortie pour ça.

### Le squelette d'une section

`# N. Titre [Cx]` + une phrase `**Objectif** : …` · puis, s'il y a lieu, une **cellule de code de
préambule** (imports, réglages, artefacts et leurs liens) · puis les `## N.n` numérotés · et, quand
elle acte un produit, une ligne `✅` de clôture.

- **Les niveaux `###`/`####` structurent librement** une sous-section longue — interprétation,
  contrôles, bilan. On titre ce qui aide le lecteur, sans quota ni réservation à un usage unique ;
  deux sorties de même nature peuvent aussi se distinguer par une étiquette `**> Libellé**`.
- **Un titre de sous-section est un groupe nominal** — `## 5.2 Profilage des colonnes`. Une à deux
  phrases d'intention sont admises avant la sortie ; on évite seulement d'interpréter à l'avance une
  sortie qu'on n'a pas encore montrée.
- **Voix** : encarts et phrases d'intention à la **première personne** ; `Constat ⇒ Décision` et
  `✅` impersonnels.

### Blocs de lecture (patrons recommandés)

Sous une sortie, un **bloc de lecture** court ou rien. Les gabarits ci-dessous donnent la
régularité ; ce sont des patrons recommandés, pas un carcan à compter.

```
**Constat ⇒ Décision**

- **40 paires strictement identiques** sur les 33 colonnes ⇒ Supprimer les lignes en double
- **Erreurs de format ⇒ à normaliser** - *la valeur est juste, l'écriture non*
  - `date_inscription` (3 formats) · `taux_presence_pct` (« % » + virgule)

**⇒ Rien à mettre en forme.**
```

Le gras nomme le **défaut** (« Erreurs de format », « Valeurs hétérogènes ») plutôt que l'objet ou
l'action, et s'arrête au groupe qui porte le chiffre. La glose italique oppose deux termes. On évite
d'empiler plus de deux niveaux de puces.

```
**Cohérence à vérifier ⇒ à faire en §5.3**

- `student_id`, `id_dossier` : un même identifiant porte-t-il deux lignes **divergentes** ?

**Questions reportées ⇒ à traiter lors de l'EDA §6**

- Valeurs absentes - 10 colonnes, jusqu'à 49,29 % : mécanisme (refus, MAR…) à qualifier
```

Un report est un **en-tête gras portant sa destination**, suivi d'une à trois puces — jamais un
tableau. Toutes les annonces de contrôle d'une section sont **groupées en un seul endroit**, sous la
sortie qui les a fait naître. Un fait que la section ne tranche pas descend ici avec son chiffre,
il ne prend jamais la forme d'un `Constat ⇒ Décision`.

```
✅ 100 % d'appariement ⇒ La jointure est possible
✅ Palier **Silver** construit
```

Une cellule, une ligne, sans point final. Le `✅` de clôture de section est le plus court : il acte
le produit, sans chiffre.

```
> 🔧 **Comment je m'y prends** - …     une fois, en tête de section : comment le matériau est produit
> 🔎 **Où lire le détail complet.** …  une fois, avant la sortie tronquée : où lire ce qu'on ne montre pas
```

Les encarts 🔧 et 🔎 sont les gabarits habituels ; ce qu'un encart dit ne se redit pas ailleurs.

### Typographie

| Signe | Emploi, et lui seul |
|---|---|
| `⇒` | `constat ⇒ conséquence`, espacé. La conséquence est en minuscule (« à normaliser », « variance nulle ») ; l'impératif capitalisé est réservé à une action immédiate |
| `→` | variation avant→après, sans espaces : `` `filiere` (31→8) `` |
| ` - ` | toute incise ; **jamais** `—` ni `–` |
| `·` | sépare des groupes de même nature sur **une seule ligne** — jamais une liste à puces |
| `/` | variantes d'une même valeur : `f`/`femme` |
| `§N` | renvoi interne, sans lien |

Un tableau markdown écrit à la main est permis. Seul l'**invariant 1** le contraint : chaque chiffre
qu'il porte doit apparaître dans une sortie de cellule.

### Densité

| | Cible |
|---|---|
| cellule de commentaire | **~120 caractères** en médiane ; le plafond d'un écran vaut toujours |
| cellule de lecture d'une sortie de synthèse | jusqu'à ~1 200 caractères — le critère est *une sortie, une cellule*, pas la longueur |
| poids markdown / poids code d'une section | indicatif : rester sobre ; une section d'interprétation peut légitimement être plus bavarde |

*Le ratio markdown/code n'est pas une cible chiffrée : c'est un repère de sobriété, pas une règle.*

### Rapport au journal de bord

**Le bloc `Constat ⇒ Décision` n'est pas le journal de bord.** Il porte la conséquence *mécanique*
d'une mesure — celle qui n'a pas d'alternative défendable. Dès qu'un choix avait une alternative
sérieuse, il descend au **journal de bord** de la section, sous le gabarit de la règle 1. Une
section qui n'arbitre rien (§5) n'a pas de journal.

## Découpage des sections données (C3)

Un **palier est un état de la donnée, pas une unité de rédaction**. Et **les trois paliers naissent
en §7** : §5 et §6 constatent, mesurent, décident ; §7 agit.

| § | Rôle | Produit |
|---|---|---|
| **5** Chargement et compréhension | profiler, constater, inventorier les modalités | **jeu de travail** — conformation d'écriture, recodage, dédoublonnage. N'arbitre rien, ne perd aucune information. **Jetable** : il ne sert qu'à §6, §7 repart des fichiers reçus |
| **6** EDA | mesurer, interpréter, **décider** — sur l'ensemble du jeu | rien : aucune donnée n'est modifiée |
| **7** Préparation | repartir des fichiers reçus, rejouer les règles de §5, appliquer les décisions de §6 | **bronze** → **silver** → **gold**. La section se clôt sur le jeu de référence et ses décisions |
| **9** Entraînement | **splitter**, puis ajuster le `Pipeline` sur le train seul | partition train / test, puis imputation, encodages, scaling |

**Le bronze est la copie exacte des fichiers reçus, immuable** — rien n'y est transformé. C'est
l'assurance de pouvoir rejouer la chaîne depuis la source si une règle de conformation se révèle
fausse. Le palier conformé, recodé, dédoublonné, c'est le **silver**.

**§5 fabrique un jeu de travail, pas un palier.** Sans lui, l'EDA serait impossible — on n'explore
pas des nombres restés en texte. Mais il ne circule pas au-delà de §6 : §7 rejoue les mêmes règles
depuis le bronze, par le même code (`data/preparation.py`, `transform`), ce qui garantit que ce qui
a été exploré est bien ce qui est préparé.

**Le gold est le jeu de référence : propre, annoté, validé, lisible par un humain.** Ce n'est pas la
matrice que consomme `fit()` — celle-là est la sortie du `Pipeline`, et n'est pas un palier.
Critère d'appartenance : *si une colonne du gold n'est plus lisible telle quelle dans un tableur,
elle appartient au `Pipeline`*. `assez bien` reste `assez bien` ; un `1` à sa place, ou six colonnes
`mention_bac_*`, relèvent du `Pipeline`.

| Dans le gold (déterministe) | Dans le `Pipeline` (apprend, donc après le split) |
|---|---|
| exclusions de principe, dérivations ligne à ligne (`taux_rendu`) | imputation, one-hot, encodage ordinal, scaling |

**L'exploration porte sur l'ensemble du jeu** — décrire les données, c'est les décrire toutes, et
c'est ce qui garantit qu'aucune modalité rare ne manque à l'inventaire. Deux garde-fous :

- **Le vocabulaire catégoriel est déclaré, jamais déduit** — `preparation.CANONICAL_MODALITIES` fait foi,
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

**Le préprocessing appris reste dans le `Pipeline`, ré-ajusté à chaque pli.** Imputation, encodages
et scaling se `fit` *à l'intérieur* de la validation croisée, jamais figés sur le train entier avant
elle — sinon le pli de validation fuit dans l'ajustement. §9 **ajuste** ce `Pipeline` sur le train ;
**§10 le sérialise** (C6) : l'artefact déployable se fige là, sur le modèle final éprouvé, pas avant.

### Lexique — quatre objets, un seul mot « pipeline »

« Pipeline » a servi pour quatre choses distinctes ; on les **nomme séparément**, on n'écrit jamais
« pipeline » nu.

- **La chaîne de préparation** (les *paliers*) - bronze → silver → gold, en pandas
  (`preparation.transform`). **Déterministe** : aucune statistique apprise des données ; c'est de
  l'ETL, **pas un `Pipeline` sklearn**. Vit en §5 (jeu de travail jetable) et §7 (paliers). « Rejouer
  la chaîne depuis la source » la désigne, elle.
- **Le préprocesseur** - un `ColumnTransformer` qui applique les transformations **apprises** :
  imputation, one-hot / encodage ordinal, scaling. Il apprend ses paramètres (médiane, vocabulaire,
  moyenne/écart-type) ⇒ `fit` sur le train seul, **après le split**. C'est ce que la table
  gold/`Pipeline` ci-dessus nomme `Pipeline`.
- **Le pipeline modèle** - un `Pipeline([préprocesseur, estimateur])` : préprocesseur **et** modèle
  enchaînés en un objet `fit`/`predict` unique. C'est lui qu'on ajuste et qu'on valide en **§9** ; le
  préprocesseur étant dedans, la validation croisée le ré-ajuste à chaque pli - **sans fuite**.
- **Le pipeline déployé** - le pipeline modèle final, `fit`, éprouvé (§12), puis **sérialisé**
  (`joblib`) et emballé d'un `predict()` + contrat d'entrée/sortie. L'artefact **déployable** de
  **§10** (C6). Même objet que le pipeline modèle, figé pour la production.

Les trois derniers sont **le même objet à trois stades** : le préprocesseur *dans* le pipeline
modèle, `fit` en §9, sérialisé en §10. Seule la **chaîne** (premier point) est d'une autre nature.

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

**Le code porte le verbe, le notebook porte le complément.** Une fonction testée dit *comment*
mesurer, vérifier, transformer ; *quoi* vérifier et *pourquoi* se déclare dans le notebook, à la
section où la mesure le fonde, et lui est **passé en paramètre**. Un module ne porte donc aucune
table de jugement — thèmes, horizon de prédiction, bornes de domaine, exclusions : ce sont des
propositions, et une proposition se défend là où le jury la lit. Test décisif : *une table qui porte
une colonne « motif » est un journal de bord déguisé*.

Deux exceptions, et elles se justifient d'elles-mêmes : ce que la **mise en forme applique** (le
vocabulaire de recodage vit dans `data/preparation.py`, parce qu'il fabrique le jeu conformé), et ce
qu'aucun choix ne gouverne (une constante de convention, une palette). **§10 industrialise** ce que le notebook a
démontré — c'est là que les déclarations éprouvées se figent en artefact déployable, pas avant.

**Dans le notebook, en plus.**

- **`display()`, jamais `print()`** — d'un `DataFrame` ou d'un `Markdown`. Aucun alignement à coups
  d'espaces, aucun `display()` sous un `if` : le filtre passe dans la compréhension qui construit
  le contenu, la sortie existe à chaque exécution.
- **Le code écrit la phrase.** Tout chiffre affiché sort d'une f-string, valeur en gras — jamais
  retapé en markdown, jamais redit par la cellule de lecture qui suit.
- **Une sortie porte son étiquette** quand un titre ne la nomme pas :
  `display(Markdown("**> Étudiants**"))`, groupe nominal seul, sans chiffre.
- **Trois mesures hétérogènes ou plus ⇒ un `DataFrame` à deux colonnes** (`set_index("Mesure")`,
  valeurs déjà formatées en chaînes, cas vide écrit `"aucune"`). En deçà, une boucle qui émet une
  puce `Markdown` par cas. Trois mesures homogènes tiennent sur **une ligne séparée par `·`**.
- **Une cellule de code peut émettre plusieurs `display()`** de natures différentes — le tableau,
  puis la ligne qui le qualifie. La règle « une sortie, une cellule » ne vise que le markdown.
- **Les variables locales du notebook suivent le vocabulaire métier, en français** — `jumelles`,
  `conflits`, `appariables`, `orphelines`. L'anglais reste la règle dans `src/`.
- **Commentaires rares, mais présents** : deux lignes au plus, pour justifier ce que le code fait
  quand ce n'est pas évident (normaliser avant de comparer, effet de bord d'un paramètre).

## Avant commit

Un commit ne se fait **que sur demande explicite de Julien**. Le feu vert donné :

1. **Documentation à jour** — `README.md`, `CLAUDE.md` reflètent l'état réel du code.
2. **Aucune référence morte**, aucun fichier versionné citant `docs/local/<fichier>`.
3. **Revue du `git diff --staged`** — pas de `print` de debug, pas de code mort, et aucune ressource
   non versionnée stagée (`data/`, `models/`, `reports/`, `docs/local/`, `*.local.ipynb`).
4. **Message conventionnel** (`feat` / `fix` / `docs` / `refactor`), **commit atomique**.
