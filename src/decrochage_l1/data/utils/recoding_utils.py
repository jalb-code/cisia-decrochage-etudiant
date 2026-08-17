"""Recodage du vocabulaire catégoriel : synonymes ramenés à une forme canonique.

Le recodage n'est **pas** une mise en forme : rapprocher `f` et `femme` suppose un
**vocabulaire cible**, donc une décision - le choix du libellé de référence. C'est
pourquoi il ne vit ni dans `cleaning_utils` (primitives sans vocabulaire) ni dans
`profiling_utils` (qui ne fait que mesurer), mais dans ce module dédié.

Ce module ne porte que le **mécanisme**, agnostique du cas d'usage : il reçoit un
`vocabulary` en paramètre et n'en connaît aucun. La table métier (`CANONICAL_MODALITIES`)
vit dans `data.preparation`, qui fabrique le jeu conformé et l'y injecte. Le même
mécanisme sert ainsi le notebook (§5) et la construction des paliers, sans jamais
figer de connaissance métier ici.

Recoder ne perd aucune information : cela cesse de compter une valeur pour plusieurs.
Aucune ligne, aucune colonne, aucun manquant n'est touché.

Deux conventions gouvernent un vocabulaire cible :

- il est orienté **forme canonique -> écritures qu'elle absorbe** (`{"femme": ("f",
  "femme")}`), parce que c'est le sens qui se **relit** : on voit le groupe, pas une
  liste de correspondances plates ;
- les clés sont les modalités **déjà normalisées** (`cleaning_utils.normalize_text`) :
  `"Femme"`, `"femme"` et `" FEMME "` sont entrées dans le même `femme` avant d'arriver
  ici. Une modalité absente de la table est **laissée telle quelle** - le recodage ne
  supprime rien et n'invente rien.
"""

import pandas as pd

Vocabulary = dict[str, dict[str, tuple[str, ...]]]


def canonical_by_variant(column: str, vocabulary: Vocabulary) -> dict[str, str]:
    """Correspondance inverse - écriture normalisée vers forme canonique.

    C'est la forme que consomme `Series.replace` ; le `vocabulary` reste orienté dans
    l'autre sens (forme -> variantes) parce que c'est celui qui se **relit**. Le
    vocabulaire est **passé**, jamais deviné : c'est ce qui rend le mécanisme
    agnostique du cas d'usage.
    """
    return {
        variant: canonical
        for canonical, variants in vocabulary.get(column, {}).items()
        for variant in variants
    }


def recode(data: pd.DataFrame, vocabulary: Vocabulary) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Ramène les modalités synonymes à leur forme canonique selon un `vocabulary`.

    Le vocabulaire cible est **passé** : le mécanisme ne porte aucune connaissance
    métier, seule la table en porte. S'attend à des valeurs **déjà normalisées**
    (`cleaning_utils.normalize_text`) : les clés du vocabulaire le sont. Ne touche
    qu'aux colonnes présentes **à la fois** dans le jeu et dans le vocabulaire : le
    même code traite les étudiants et le catalogue sans savoir lequel il reçoit. Rend
    aussi la liste des colonnes effectivement recodées - un fait à afficher, pas une
    trace de débogage.
    """
    result = data.copy()
    recoded: list[str] = []

    for column in result.columns:
        correspondance = canonical_by_variant(str(column), vocabulary)
        if not correspondance:
            continue
        result[column] = result[column].replace(correspondance)
        recoded.append(str(column))

    return result, tuple(recoded)
