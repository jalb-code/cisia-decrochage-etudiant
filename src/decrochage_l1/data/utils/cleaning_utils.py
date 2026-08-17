"""Nettoyage — primitives déterministes de mise en forme des valeurs.

Chaque fonction d'ici est **pure** : elle ne lit aucune configuration, n'apprend
aucun paramètre à partir des données et ne connaît aucune colonne du cas d'usage.
Elle reçoit une `Series`, elle en rend une.

Ce qu'elles font : ramener plusieurs **écritures** d'une même valeur à une seule
forme. `"12.0 km"` et `"12,0"` deviennent le même `12.0` parce qu'ils *disent
déjà* la même chose.

Ce qu'elles ne font pas : **recoder**. Rapprocher `"F"` et `"Femme"` suppose un
vocabulaire cible, donc un arbitrage — hors du champ d'une primitive. Aucune ne
supprime de ligne, de colonne ni de modalité, aucune ne traite un manquant
autrement qu'en le laissant manquant.

D'où l'invariant qui les rend réutilisables : le résultat ne dépend **ni de
l'ordre des appels, ni de la taille du lot**. Une ligne isolée donne exactement
ce que donnerait le fichier entier. C'est ce qui permet à `profiling` de s'en
servir pour mesurer un CSV dont il ne sait rien à l'avance.
"""

import pandas as pd

# Marques diacritiques Unicode : après décomposition NFKD, "é" devient "e" + U+0301.
# Les retirer par regex évite un aller-retour encode/decode ASCII, dont le
# comportement dépend du dtype de la Series (str natif vs string pandas).
_DIACRITICS = r"[̀-ͯ]"


def blank_to_na(values: pd.Series) -> pd.Series:
    """Ramène les cellules vides ou blanches à un manquant explicite.

    Règle unique du projet : **un blanc est une absence, jamais une modalité.**
    Sans elle, `""` survit comme catégorie de plein droit et gonfle silencieusement
    le nombre de modalités d'une colonne — un décompte faux, sur lequel toute
    lecture ultérieure s'appuierait.

    Elle rend surtout le traitement **insensible à l'écriture de l'absence** :
    `""`, `"   "` et `NaN` donnent le même résultat.
    """
    text = values.astype("string")
    return text.mask(text.fillna("").str.strip() == "", pd.NA)


def normalize_text(values: pd.Series) -> pd.Series:
    """Minuscules, sans accent, sans espaces superflus — forme de comparaison.

    Ramène les variantes d'écriture d'une même valeur (`" Gestion "`, `"GESTION"`,
    `"gestion"`) à une clé unique, et les variantes accentuées (`"Général"`,
    `"general"`) avec elles. Les valeurs manquantes — blancs compris — restent
    manquantes.

    Le résultat est une **clé de rapprochement**, pas une valeur d'affichage :
    elle sert à constater que deux cellules disent la même chose, jamais à
    remplacer ce qu'elles disent.
    """
    return (
        blank_to_na(values)
        .str.strip()
        .str.lower()
        .str.normalize("NFKD")
        .str.replace(_DIACRITICS, "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
    )


def parse_number(values: pd.Series, units: tuple[str, ...] = ()) -> pd.Series:
    """Convertit un nombre stocké en texte en `float`.

    Gère les écritures qui ne changent rien à la valeur : séparateur décimal point
    ou virgule, et unité collée au nombre (`"12.0 km"`, `"77.5%"`) — les unités à
    retirer sont passées par l'appelant, la fonction n'en devine aucune.

    Une valeur inconvertible devient `NaN` plutôt que de lever : c'est ce qui
    permet de **mesurer** le taux de non-conformité d'une colonne au lieu de
    s'arrêter à la première anomalie.
    """
    text = values.astype("string")
    for unit in units:
        text = text.str.replace(unit, "", case=False, regex=False)
    text = text.str.replace(",", ".", regex=False).str.replace(r"\s+", "", regex=True)
    return pd.to_numeric(text, errors="coerce")


def parse_date(values: pd.Series, formats: tuple[str, ...]) -> pd.Series:
    """Parse une colonne de dates écrites dans plusieurs formats.

    Les formats sont essayés dans l'ordre, chacun explicitement — et non via
    `format="mixed"`, qui devine et peut inverser jour et mois. Ils sont fournis
    par l'appelant : la fonction n'en suppose aucun.

    Une valeur qu'aucun format ne reconnaît reste `NaT`, pour la même raison que
    `parse_number` rend `NaN` — l'anomalie se compte, elle n'interrompt pas.
    """
    text = values.astype("string")
    result = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    for date_format in formats:
        pending = result.isna() & text.notna()
        if not pending.any():
            break
        result[pending] = pd.to_datetime(text[pending], format=date_format, errors="coerce")
    return result
