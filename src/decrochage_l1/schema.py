"""Vocabulaire cible du recodage : la forme canonique de chaque modalité.

Ce module ne porte que des **données**, aucune logique — l'application vit dans
`data.bronze`. Il répond à une seule question : quand plusieurs libellés
désignent la même valeur, lequel fait foi ?

Trois conventions le gouvernent :

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
# (colonne inférieure, colonne supérieure). Ce sont les seules contraintes
# falsifiables que l'énoncé pose entre colonnes ; elles échappent au profil, qui
# raisonne colonne par colonne. La mécanique de vérification est générique et vit
# dans `data.profiling` — seule la liste, métier, est déclarée ici.
ORDER_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("nb_devoirs_rendus", "nb_devoirs_total"),
    ("nb_ue_validees_s1", "nb_ue_total"),
)


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
