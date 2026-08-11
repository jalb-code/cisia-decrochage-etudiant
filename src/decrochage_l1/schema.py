"""Vocabulaire et grille de lecture du jeu de données — les choix que le code applique.

Ce module ne porte que des **déclarations**, jamais de traitement : l'application
vit dans `data.bronze` et dans le notebook. Il répond à deux questions.

**Quand plusieurs libellés désignent la même valeur, lequel fait foi ?**
(`CANONICAL_MODALITIES`, ci-dessous.)

**Que représentent ces trente-trois colonnes, prises ensemble ?**
(`COLUMN_THEMES`, en fin de module.) Attention à ce que cette seconde table est et
n'est pas : le regroupement des colonnes par thème est un **jugement de lecture**,
posé à la main d'après le *sens* des colonnes. Aucune mesure ne le fonde et aucune
fonction ne le valide. Ce que le code garantit se limite à deux propriétés
vérifiables — toute colonne du jeu est classée quelque part, et aucun thème ne
cite une colonne qui n'existe pas (`unclassified`, `unknown`). L'exhaustivité se
teste ; la pertinence se défend.

Trois conventions gouvernent le vocabulaire cible :

- la forme canonique est le **libellé complet**, en écriture normalisée
  (minuscules, sans accent) — `femme` et non `f`, `passable` et non `p`. Une
  abréviation est illisible dans un graphique comme dans une restitution
  d'explicabilité ;
- les clés sont les modalités **déjà normalisées** par `cleaning.normalize_text`,
  jamais les écritures brutes : `"Femme"`, `"femme"` et `" FEMME "` sont entrées
  dans le même `femme` avant d'arriver ici ;
- une modalité absente de ces tables est **laissée telle quelle**. Le recodage ne
  supprime rien et n'invente rien ; une valeur inattendue reste visible dans
  l'inventaire des modalités plutôt que d'être silencieusement absorbée.

Deux choix méritent leur justification, parce qu'ils ne vont pas de soi :

- **`autre` et `inconnu` ne fusionnent pas** sur `sexe`. `nb` et `autre` sont des
  identités déclarées, `nr` une absence de réponse. Les confondre mêlerait une
  information à son absence, et ferait disparaître les personnes non binaires
  dans un fourre-tout ;
- **`boursier` reste `oui`/`non`**, en texte. Le passer en 0/1 serait un
  *encodage* de variable, au même titre qu'un *one-hot* ou un ordinal — cela
  relève de la préparation (§7), pas du palier bronze.

Les colonnes absentes d'ici (`filiere`, `etablissement_origine`) n'ont aucun
synonyme : uniformiser leur écriture suffit à les ramener à leurs modalités.
"""

from collections.abc import Iterable

# Forme canonique -> écritures normalisées qu'elle absorbe. Cette orientation est
# celle qui se relit : on voit le groupe, pas une liste de correspondances plates.
CANONICAL_MODALITIES: dict[str, dict[str, tuple[str, ...]]] = {
    "sexe": {
        "femme": ("f", "femme"),
        "homme": ("h", "m", "homme"),
        "autre": ("nb", "autre"),
        "inconnu": ("nr",),
    },
    "bac_type": {
        "general": ("gen", "general", "generale"),
        "technologique": ("techno", "technologique"),
        "professionnel": ("pro", "professionnel"),
    },
    "mention_bac": {
        "passable": ("p", "passable"),
        "assez bien": ("ab", "assez bien"),
        "bien": ("b", "bien"),
        "tres bien": ("tb", "tres bien"),
    },
    "boursier": {
        "oui": ("o", "oui", "1"),
        "non": ("n", "non", "0"),
    },
}


# Inégalités que deux colonnes doivent respecter **ligne à ligne**, sous la forme
# (colonne inférieure, colonne supérieure). Elles échappent au profil, qui raisonne
# colonne par colonne : des maximums égaux de part et d'autre ne disent rien d'un
# croisement ligne à ligne. La mécanique de vérification est générique et vit dans
# `data.profiling` — seule la liste, métier, est déclarée ici.
#
# Ce ne sont pas les seules relations entre colonnes que l'énoncé pose : il décrit
# aussi `jour_inscription` comme le « jour réel de la date » d'inscription, ce qui
# est une dérivation et non une inégalité — donc une autre mécanique.
ORDER_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("nb_devoirs_rendus", "nb_devoirs_total"),
    ("nb_ue_validees_s1", "nb_ue_total"),
)


# Grille de lecture : ce que les colonnes représentent ensemble. **Découpage posé à
# la main**, d'après le sens des colonnes — cf. la docstring du module sur ce que
# cette table n'est pas. Il sert en aval : §7 arbitre par familles et §12 restitue
# l'explicabilité par catégorie métier, un tuteur comprenant « assiduité en baisse »
# plutôt que « nb_devoirs_rendus = 3 ».
COLUMN_THEMES: dict[str, tuple[str, ...]] = {
    "Identifiants": ("student_id", "id_dossier"),
    "Contexte d'inscription": ("annee_universitaire", "filiere", "date_inscription"),
    "Profil social et démographique": (
        "age",
        "sexe",
        "boursier",
        "distance_domicile_km",
        "heures_travail_remunere_sem",
    ),
    "Parcours antérieur": ("bac_type", "mention_bac", "etablissement_origine"),
    "Engagement LMS": (
        "connexions_lms_30j",
        "heures_lms_total",
        "ressources_consultees",
        "messages_forum",
    ),
    "Assiduité et travail rendu": (
        "taux_presence_pct",
        "retards_rendus",
        "nb_devoirs_total",
        "nb_devoirs_rendus",
    ),
    "Résultats académiques": ("moyenne_partiels_s1", "nb_ue_total", "nb_ue_validees_s1"),
    "Ressenti déclaré": ("motivation", "satisfaction", "sentiment_appartenance"),
    "Avis du tuteur": ("commentaire_tuteur",),
    "Leurres annoncés": ("groupe_td", "couleur_carte_etudiante", "jour_inscription"),
    "Cibles": ("abandon", "moyenne_finale"),
}


def canonical_by_variant(column: str) -> dict[str, str]:
    """Correspondance inverse — écriture normalisée vers forme canonique.

    C'est la forme que consomme `Series.replace` ; `CANONICAL_MODALITIES` reste
    orienté dans l'autre sens parce que c'est celui qui se **relit**.
    """
    return {
        variant: canonical
        for canonical, variants in CANONICAL_MODALITIES.get(column, {}).items()
        for variant in variants
    }


def theme_by_column() -> dict[str, str]:
    """Correspondance inverse — nom de colonne vers son thème.

    `COLUMN_THEMES` reste orienté dans l'autre sens parce que c'est celui qui se
    relit : on voit le groupe, pas une liste plate.
    """
    return {column: theme for theme, columns in COLUMN_THEMES.items() for column in columns}


def unclassified(columns: Iterable[str]) -> tuple[str, ...]:
    """Colonnes du jeu qu'aucun thème ne cite — la grille n'est plus exhaustive.

    À afficher plutôt qu'à taire : une colonne non classée est un trou dans la
    lecture métier, et elle passerait inaperçue dans un tableau écrit à la main.
    """
    classes = theme_by_column()
    return tuple(column for column in columns if column not in classes)


def unknown(columns: Iterable[str]) -> tuple[str, ...]:
    """Colonnes citées par un thème mais absentes du jeu — la grille a vieilli.

    Le cas symétrique de `unclassified`, et le plus sournois : un renommage de
    colonne laisse la grille intacte et silencieusement fausse.
    """
    presentes = set(columns)
    return tuple(column for column in theme_by_column() if column not in presentes)
