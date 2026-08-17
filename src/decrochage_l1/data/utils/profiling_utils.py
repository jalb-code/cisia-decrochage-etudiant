"""Profilage d'un CSV : encodage, délimiteur, types, motifs d'écriture, non-conformité.

Le module déduit tout du contenu : il ne reçoit qu'un chemin de fichier. Il
**mesure**, il ne transforme pas : `profile_csv` rend encodage, délimiteur, type
réel de chaque colonne (celui que pandas lui attribue spontanément), type
sémantique (ce qu'elle représente), motifs d'écriture, bornes des colonnes
ordonnables (nombres et dates), taux de manquants et de non-conformité. La mise
en forme pilotée par ce profil (`conform`) vit dans `data.preparation`, qui
fabrique le jeu conformé ; ici, rien n'est modifié.

Le profil se lit à deux niveaux, pour une seule mesure : `CsvProfile.overview()`
en donne les huit indicateurs qui tiennent à l'écran, et le **rapport HTML** —
optionnel, délégué à `profiling_report` — les quatorze au complet, modalités
énumérées.

Aucune fonction ne supprime de ligne ou de colonne, ne fusionne deux modalités,
ni ne remplace un manquant : le module ne fait que constater.

Les primitives sur lesquelles s'appuie la mesure (`normalize_text`, `parse_number`,
`parse_date`) viennent de `data.utils.cleaning_utils`.
"""

import codecs
import csv
import re
from dataclasses import dataclass, replace
from itertools import groupby
from pathlib import Path

import pandas as pd

from decrochage_l1.data.utils import cleaning_utils as cleaning
from decrochage_l1.data.utils import profiling_report

# --- Détection d'encodage -----------------------------------------------------
# UTF-32 avant UTF-16 : la marque UTF-32-LE (FF FE 00 00) commence par celle de
# l'UTF-16-LE (FF FE), donc l'ordre inverse produirait un faux positif.
_BOM_ENCODINGS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

# Essayés dans l'ordre en l'absence de marque d'ordre. `cp1252` avant `latin-1` :
# le second décode n'importe quel octet, donc il ne peut jamais échouer et
# masquerait le vrai encodage s'il passait en premier.
_FALLBACK_ENCODINGS: tuple[str, ...] = ("utf-8", "cp1252", "latin-1")

_DELIMITER_CANDIDATES = ",;\t|"

# --- Vocabulaires de détection sémantique -------------------------------------
# Écritures booléennes courantes, sous forme normalisée. Un mot isolé n'y suffit
# pas : la colonne entière doit tenir dans ce vocabulaire (cf. `_is_boolean`).
_BOOLEAN_VOCABULARY = frozenset(
    {"0", "1", "oui", "non", "o", "n", "true", "false", "vrai", "faux", "yes", "no", "y", "t", "f"}
)

# Marqueurs d'absence écrits *en toutes lettres*. Ils ne sont PAS traités comme
# des manquants — les convertir serait une décision — mais signalés en remarque :
# une source qui écrit "N/A" dans une colonne numérique doit se voir.
_NULL_SENTINELS = frozenset({"na", "n/a", "nan", "null", "none", "nc", "n.c.", "-", "?", "."})

# Formats de date candidats, du plus normalisé au plus rare. L'ordre ne fixe
# rien : la sélection est gloutonne (cf. `detect_date_formats`), il n'influe que
# sur les ex æquo — d'où le jour-mois (usage francophone) avant le mois-jour.
_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%d/%m/%y",
    "%Y-%m-%d %H:%M:%S",
)

# Part des valeurs qu'un type doit couvrir, en lecture *tolérante*, pour être
# retenu. En dessous de 1, une colonne numérique salie par quelques valeurs
# aberrantes reste reconnue comme numérique — et la salissure ressort dans
# `pct_non_conforme` au lieu de faire basculer la colonne en « texte ».
_TYPE_COVERAGE = 0.95

# Une colonne est dite catégorielle si ses modalités sont peu nombreuses *et*
# rares au regard du volume : le second critère évite de qualifier de
# catégorielle une colonne de 20 valeurs sur un fichier de 20 lignes.
_CATEGORICAL_MAX_DISTINCT = 50
_CATEGORICAL_MAX_RATIO = 0.10

# Une colonne quasi entièrement distincte est une clé candidate. Le seuil est
# < 1 à dessein : une clé reste reconnue *malgré* quelques doublons, là où une
# égalité stricte la manquerait. Le plancher de lignes évite l'absurde : sur un
# fichier de 8 lignes, toute colonne un peu variée paraît unique.
_IDENTIFIER_MIN_RATIO = 0.95
_IDENTIFIER_MIN_ROWS = 30

# Types sémantiques dont l'écriture obéit à une forme canonique : seuls ceux-là
# rendent le comptage des motifs interprétable (cf. `pattern_is_informative`).
_PATTERNED_TYPES = frozenset({"entier", "decimal", "date", "identifiant"})

# Échantillon utilisé pour les tests coûteux (dates) lors de l'inférence de type.
_INFERENCE_SAMPLE = 400

# Plafond d'énumération des modalités (`modality_breakdown`) : garde d'**utilité**,
# pas de performance — au-delà, la liste cesse d'être lisible et le profil chiffré
# suffit. Surchargeable à l'appel.
_MAX_MODALITIES = 20

# Même garde pour les motifs d'écriture (`pattern_breakdown`). Le plafond est plus
# bas : une colonne bien formée en compte un ou deux, et au-delà d'une dizaine le
# motif cesse de décrire une convention pour décrire chaque valeur.
_MAX_PATTERNS = 12

# Vue resserrée du profil, pour la lecture à l'écran : ce qu'une colonne est,
# combien de modalités elle porte (brutes et normalisées), ses bornes, son taux
# de manquants. Les six autres indicateurs restent dans `CsvProfile.columns` et
# sont restitués par le rapport HTML — une seule mesure, deux restitutions.
_OVERVIEW_COLUMNS = (
    "colonne",
    "type_reel",
    "type_semantique",
    "n_distinct",
    "n_distinct_normalise",
    "min",
    "max",
    "null_%",
)


@dataclass(frozen=True)
class FileProfile:
    """Ce qu'on sait du fichier lui-même, indépendamment de son contenu métier."""

    path: Path
    encoding: str
    has_bom: bool
    delimiter: str
    n_rows: int
    n_columns: int
    n_duplicate_rows: int
    size_bytes: int

    def to_frame(self) -> pd.DataFrame:
        """Vue tabulaire à deux colonnes, pour l'affichage dans un notebook."""
        delimiter = {"\t": "\\t"}.get(self.delimiter, self.delimiter)
        rows = {
            "Fichier": self.path.name,
            "Encodage": f"{self.encoding} ({'avec' if self.has_bom else 'sans'} BOM)",
            "Délimiteur": f"« {delimiter} »",
            "Lignes": f"{self.n_rows:,}".replace(",", " "),
            "Colonnes": str(self.n_columns),
            "Lignes en double": str(self.n_duplicate_rows),
            "Taille": f"{self.size_bytes / 1024:.1f} Kio",
        }
        return pd.DataFrame({"Propriété": list(rows), "Valeur": list(rows.values())})


@dataclass(frozen=True)
class CsvProfile:
    """Résultat complet d'un profilage : le fichier, ses colonnes, ses données brutes."""

    file: FileProfile
    columns: pd.DataFrame
    data: pd.DataFrame  # toutes les valeurs en texte, telles qu'écrites dans le fichier
    report_path: Path | None = None  # rapport HTML, si sa génération a été demandée

    def overview(self) -> pd.DataFrame:
        """Vue resserrée du profil de colonnes — huit indicateurs au lieu de quatorze.

        À afficher à l'écran, où quatorze colonnes forcent le repli sur plusieurs
        blocs et noient l'essentiel. Les six autres indicateurs (motif d'écriture,
        non-conformité, exemples, remarques) ne sont pas perdus : `columns` les
        porte toujours — c'est lui que filtrent les extractions de défauts — et le
        rapport HTML les restitue en entier.
        """
        return self.columns[list(_OVERVIEW_COLUMNS)]


# =============================================================================
#  NIVEAU FICHIER — encodage, délimiteur, lecture brute
# =============================================================================


def detect_encoding(path: Path) -> tuple[str, bool]:
    """Déduit l'encodage d'un fichier texte ; retourne aussi la présence d'un BOM.

    Deux temps : la marque d'ordre des octets si elle existe (preuve, pas
    supposition), sinon un décodage d'essai du fichier entier. Décoder tout
    plutôt qu'un échantillon est délibéré — un caractère accentué isolé en fin de
    fichier suffit à départager UTF-8 et CP1252, et le manquer donnerait des
    « Ã© » silencieux à la lecture.
    """
    path = Path(path)
    head = path.read_bytes()[:4]
    for bom, encoding in _BOM_ENCODINGS:
        if head.startswith(bom):
            return encoding, True

    payload = path.read_bytes()
    for encoding in _FALLBACK_ENCODINGS:
        try:
            payload.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding, False
    return "latin-1", False


def detect_delimiter(path: Path, encoding: str) -> str:
    """Déduit le séparateur de champs par sniffing, avec repli sur un comptage.

    Le `Sniffer` de la bibliothèque standard échoue sur les fichiers à une seule
    colonne ou aux champs très hétérogènes ; le repli retient alors le candidat
    le plus fréquent dans l'en-tête, qui est la ligne la plus régulière.
    """
    sample = Path(path).read_text(encoding=encoding, errors="replace")[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIMITER_CANDIDATES).delimiter
    except csv.Error:
        header = sample.splitlines()[0] if sample.splitlines() else ""
        return max(_DELIMITER_CANDIDATES, key=header.count)


def read_as_text(path: Path) -> tuple[pd.DataFrame, FileProfile]:
    """Lit le CSV **sans rien interpréter** : toutes les valeurs restent du texte.

    `keep_default_na=False` neutralise la liste de manquants de pandas, qui
    convertirait silencieusement « NA », « null » ou « None » en `NaN` — on ne
    distinguerait plus une cellule vide d'une cellule où quelqu'un a *écrit*
    « N/A ». Seul le vide (ou les blancs) compte ici comme manquant ; les
    sentinelles écrites sont signalées en remarque.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    encoding, has_bom = detect_encoding(path)
    delimiter = detect_delimiter(path, encoding)
    data = pd.read_csv(
        path,
        sep=delimiter,
        encoding=encoding,
        dtype=str,
        keep_default_na=False,
        na_values=[],
    )
    profile = FileProfile(
        path=path,
        encoding=encoding,
        has_bom=has_bom,
        delimiter=delimiter,
        n_rows=len(data),
        n_columns=data.shape[1],
        n_duplicate_rows=int(data.duplicated().sum()),
        size_bytes=path.stat().st_size,
    )
    return data, profile


def read_inferred_dtypes(path: Path, profile: FileProfile) -> pd.Series:
    """Types que pandas attribue **spontanément**, sans consigne de lecture.

    C'est le « type réel » du profil, à confronter au type sémantique déduit :
    une colonne de nombres lue en `object` signale une valeur textuelle intruse
    (`"12.0 km"`, `"77,5%"`) que le seul nom de colonne ne laissait pas
    soupçonner.
    """
    frame = pd.read_csv(path, sep=profile.delimiter, encoding=profile.encoding)
    return frame.dtypes.astype(str)


# =============================================================================
#  NIVEAU VALEUR — motifs, types, unités, formats
# =============================================================================


def _filled(values: pd.Series) -> pd.Series:
    """Valeurs réellement renseignées : ni absentes, ni vides, ni blanches.

    La règle « un blanc est une absence » vit dans `cleaning.blank_to_na` — une seule
    fois pour le projet entier, profilage et nettoyage compris.
    """
    return cleaning.blank_to_na(values).dropna()


def _char_class(char: str) -> str:
    """Classe de caractère d'un motif généralisé : chiffre, lettre, ou littéral."""
    if char.isdigit():
        return r"\d"
    if char.isalpha():
        return r"\w"
    return re.escape(char)


def generalize_pattern(value: str, max_length: int = 48) -> str:
    """Réduit une valeur à son motif de forme, en syntaxe d'expression régulière.

    `"2024-09-27"` devient `\\d{4}-\\d{2}-\\d{2}`, `"04 Sep 2024"` devient
    `\\d{2} \\w{3} \\d{4}`. Le motif est ce qui rend une anomalie de format
    *visible sans lire les valeurs* : deux motifs majoritaires dans une même
    colonne, c'est une source qui mélange deux conventions d'écriture.
    """
    parts = []
    for token, run in groupby(str(value), _char_class):
        count = sum(1 for _ in run)
        parts.append(token if count == 1 else f"{token}{{{count}}}")
    pattern = "".join(parts)
    return pattern if len(pattern) <= max_length else pattern[:max_length] + "…"


def _is_stored_as_text(dtype: str) -> bool:
    """Vrai si pandas n'a **pas** su typer la colonne — donc si son écriture est en cause.

    Un `dtype` inconnu (chaîne vide) est traité comme du texte : les valeurs
    viennent de `read_as_text`, qui n'interprète rien.
    """
    return not dtype.startswith(("int", "uint", "float", "bool", "datetime", "timedelta"))


def pattern_is_informative(semantic_type: str, dtype: str) -> bool:
    """Vrai si compter les formes d'écriture d'une colonne apprend quelque chose.

    Deux conditions, cumulatives :

    - la colonne doit être **restée en texte** à la lecture. Si pandas a su la
      typer (`int64`, `float64`, `datetime64`), son écriture est homogène par
      construction et le motif ne dirait plus que son ordre de grandeur — `\\d`
      face à `\\d{2}`, c'est 9 face à 12, pas un défaut ;
    - son type sémantique doit avoir une **forme canonique écrite** (nombre, date,
      identifiant) : plusieurs motifs y signalent alors plusieurs conventions
      mêlées. Un texte libre ou une catégorie n'en a aucune — chaque longueur de
      libellé fait son propre motif (19 phrases types, 19 motifs), et
      l'hétérogénéité qui compte là, casse et espaces, est justement celle que le
      motif **ignore** : elle se lit sur `n_distinct` face à
      `n_distinct_normalise`.

    Angle mort assumé : une écriture hétérogène que pandas absorbe silencieusement
    (zéros de tête, `"1e3"` face à `"1000"`) échappe alors au motif. Aucun cas dans
    la source, et le prix est faible devant le bruit évité.
    """
    return _is_stored_as_text(dtype) and semantic_type in _PATTERNED_TYPES


def detect_units(values: pd.Series) -> tuple[str, ...]:
    """Suffixes non numériques collés aux valeurs (`"km"`, `"%"`, `"€"`)."""
    suffixes = _filled(values).str.extract(r"([^\d\s,.]+)\s*$", expand=False)
    return tuple(sorted(suffixes.dropna().unique()))


def _to_number(values: pd.Series) -> pd.Series:
    """Lecture numérique **tolérante** : virgule décimale et unité collée admises.

    Sert à décider *ce que la colonne représente*, pas à juger sa propreté — ce
    second rôle revient au motif canonique de `_conformity_rate`.
    """
    units = detect_units(values)
    return cleaning.parse_number(values, units)


def detect_date_formats(
    values: pd.Series, candidates: tuple[str, ...] = _DATE_FORMATS
) -> tuple[str, ...]:
    """Jeu minimal de formats couvrant la colonne, du plus fréquent au plus rare.

    Sélection **gloutonne** : à chaque tour on retient le format qui lit le plus
    de valeurs encore illisibles, jusqu'à épuisement. Une colonne de dates
    homogène rend donc un seul format ; en rendre trois signale une source qui
    mélange les conventions d'écriture.
    """
    text = _filled(values)
    if text.empty:
        return ()

    pending = text
    chosen: list[str] = []
    while not pending.empty:
        best_format, best_parsed = None, None
        for date_format in candidates:
            parsed = pd.to_datetime(pending, format=date_format, errors="coerce")
            if best_parsed is None or parsed.notna().sum() > best_parsed.notna().sum():
                best_format, best_parsed = date_format, parsed
        if best_format is None or not best_parsed.notna().any():
            break
        chosen.append(best_format)
        pending = pending[best_parsed.isna()]
    return tuple(chosen)


def _is_boolean(filled: pd.Series) -> bool:
    """Vrai si toutes les valeurs tiennent dans le vocabulaire booléen usuel.

    Le test porte sur la colonne entière, jamais sur une valeur isolée : `"f"`
    est une écriture de « faux » comme de « féminin », et seul le contexte des
    autres modalités permet de trancher.
    """
    keys = set(cleaning.normalize_text(filled).dropna().unique())
    return bool(keys) and keys <= _BOOLEAN_VOCABULARY


def infer_semantic_type(values: pd.Series) -> str:
    """Déduit ce que la colonne *représente*, indépendamment de son type de stockage.

    Les tests vont du plus contraignant au plus permissif : le premier qui
    l'emporte gagne, et « texte » n'est que le refuge des colonnes qu'aucun autre
    n'a su qualifier. La lecture est tolérante (`_TYPE_COVERAGE`) : quelques
    valeurs mal écrites ne déclassent pas une colonne numérique en texte, elles
    ressortent dans `non_conforme_%`.
    """
    filled = _filled(values)
    if filled.empty:
        return "vide"

    n_distinct = filled.nunique()
    distinct_ratio = n_distinct / len(filled)
    # Une partie décimale écrite (« 0.0 », « 9,0 ») fait le décimal, même si la
    # valeur tombe juste : le type qualifie l'ÉCRITURE, pas l'arrondi. Sans cela
    # une colonne de flottants ronds passerait pour entière, et ses valeurs
    # seraient comptées non conformes à un canon qu'elles n'ont jamais visé.
    has_decimal_mark = bool(filled.str.contains(r"[.,]\d", regex=True).any())

    if n_distinct == 1:
        return "constant"
    if _is_boolean(filled):
        return "booleen"
    if (
        distinct_ratio >= _IDENTIFIER_MIN_RATIO
        and len(filled) >= _IDENTIFIER_MIN_ROWS
        and not has_decimal_mark
    ):
        return "identifiant"

    numbers = _to_number(filled)
    if numbers.notna().mean() >= _TYPE_COVERAGE:
        return "decimal" if has_decimal_mark else "entier"

    sample = filled.head(_INFERENCE_SAMPLE)
    formats = detect_date_formats(sample)
    if formats and cleaning.parse_date(sample, formats).notna().mean() >= _TYPE_COVERAGE:
        return "date"

    if n_distinct <= _CATEGORICAL_MAX_DISTINCT and distinct_ratio <= _CATEGORICAL_MAX_RATIO:
        return "categoriel"
    return "texte"


def _conformity_rate(filled: pd.Series, semantic_type: str) -> float:
    """Part des valeurs écrites dans la **forme canonique** de leur type.

    Le critère dépend du type, et c'est tout l'intérêt de la mesure :

    - numérique — point décimal, aucune unité collée : `"77,5%"` est du décimal
      *mal écrit*, la valeur est juste, la forme ne l'est pas ;
    - date — le format dominant de la colonne fait référence, les autres écritures
      comptent comme non conformes (une source homogène rend donc 100 %) ;
    - texte et catégories — l'écriture majoritaire de chaque modalité fait
      référence : `" GESTION "` est non conforme si `"Gestion"` domine.

    Aucune de ces valeurs n'est fausse : le taux mesure une **hétérogénéité
    d'écriture**, celle qui empêche de compter des modalités ou d'agréger.
    """
    if filled.empty:
        return 0.0

    if semantic_type in {"entier", "decimal"}:
        canonical = r"^[+-]?\d+$" if semantic_type == "entier" else r"^[+-]?\d+(\.\d+)?$"
        return float(filled.str.fullmatch(canonical).fillna(False).mean())

    if semantic_type == "date":
        formats = detect_date_formats(filled)
        if not formats:
            return 0.0
        dominant = pd.to_datetime(filled, format=formats[0], errors="coerce")
        return float(dominant.notna().mean())

    # Types textuels : l'écriture la plus fréquente de chaque modalité fait foi.
    keys = cleaning.normalize_text(filled)
    reference = filled.groupby(keys).transform(lambda group: group.mode().iat[0])
    return float((filled == reference).mean())


def _format_extremum(value: object, semantic_type: str) -> str:
    """Écrit une borne dans la forme canonique de son type.

    Un entier sans partie décimale (« 30 », non « 30.0 »), un décimal avec la
    sienne (« 0.0 »), une date en ISO — l'heure n'apparaissant que si elle porte
    une information.
    """
    if semantic_type == "entier":
        return f"{float(value):.0f}"
    if semantic_type == "decimal":
        return f"{float(value)}"
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S").removesuffix(" 00:00:00")


def _extent(filled: pd.Series, semantic_type: str) -> tuple[str, str]:
    """Bornes d'une colonne **ordonnable** (nombres, dates) ; vide pour les autres.

    Les bornes se lisent sur la **grandeur**, jamais sur l'écriture : la lecture
    est donc tolérante (virgule décimale, unité collée, formats de date mêlés).
    Comparé comme du texte, `"9,5"` passerait pour un maximum devant `"12.0"`, et
    `"04 Sep 2024"` pour un minimum devant `"2024-09-27"`.

    Une colonne texte, catégorielle ou booléenne ne rend rien : l'ordre
    lexicographique de ses modalités n'a aucun sens métier.
    """
    if semantic_type in {"entier", "decimal"}:
        values = _to_number(filled).dropna()
    elif semantic_type == "date":
        values = cleaning.parse_date(filled, detect_date_formats(filled)).dropna()
    else:
        return "", ""

    if values.empty:
        return "", ""
    return (
        _format_extremum(values.min(), semantic_type),
        _format_extremum(values.max(), semantic_type),
    )


def _remarks(filled: pd.Series, semantic_type: str) -> str:
    """Signaux qui ne tiennent pas dans une colonne chiffrée du profil.

    Trois familles : unités collées aux nombres, pluralité de formats de date, et
    marqueurs d'absence écrits en toutes lettres (`"N/A"`, `"NC"`) — ces derniers
    sont signalés, jamais convertis en manquants.
    """
    notes: list[str] = []

    if semantic_type in {"entier", "decimal"}:
        units = detect_units(filled)
        if units:
            notes.append("unité(s) collée(s) : " + ", ".join(f"« {u} »" for u in units))
        if filled.str.contains(",", regex=False).any():
            notes.append("virgule décimale")

    if semantic_type == "date":
        formats = detect_date_formats(filled)
        if len(formats) > 1:
            notes.append(f"{len(formats)} formats mêlés : " + ", ".join(formats))

    sentinels = sorted(set(cleaning.normalize_text(filled).dropna()) & _NULL_SENTINELS)
    if sentinels:
        notes.append("marqueur(s) d'absence écrit(s) : " + ", ".join(sentinels))

    return " ; ".join(notes)


# =============================================================================
#  NIVEAU COLONNE — assemblage du profil
# =============================================================================


def profile_column(values: pd.Series, dtype: str = "") -> dict[str, object]:
    """Profil d'une colonne : ce qu'elle contient, comment c'est écrit, ce qui cloche.

    Un indicateur **sans objet** pour la colonne reste **vide** plutôt que de
    porter un zéro qui se lirait comme une mesure : les bornes d'une catégorie
    (cf. `_extent`), le motif d'un texte libre ou d'une colonne que pandas a déjà
    typée (cf. `pattern_is_informative`).
    """
    filled = _filled(values)
    semantic_type = infer_semantic_type(values)
    patterns = (
        filled.map(generalize_pattern).value_counts()
        if pattern_is_informative(semantic_type, dtype)
        else pd.Series(dtype="int64")
    )
    minimum, maximum = _extent(filled, semantic_type)
    coverage = round(100 * patterns.iat[0] / len(filled), 1) if len(patterns) else ""

    return {
        "colonne": values.name,
        "type_reel": dtype,
        "type_semantique": semantic_type,
        "motif_dominant": patterns.index[0] if len(patterns) else "",
        "couverture_motif_%": coverage,
        "n_motifs": len(patterns) if len(patterns) else "",
        "n_distinct": int(filled.nunique()),
        "n_distinct_normalise": int(cleaning.normalize_text(filled).nunique()),
        "min": minimum,
        "max": maximum,
        "null_%": round(100 * (1 - len(filled) / len(values)), 2) if len(values) else 0.0,
        "non_conforme_%": round(100 * (1 - _conformity_rate(filled, semantic_type)), 2),
        "exemples": " | ".join(filled.drop_duplicates().head(3).astype(str)),
        "remarques": _remarks(filled, semantic_type),
    }


def profile_columns(data: pd.DataFrame, dtypes: pd.Series | None = None) -> pd.DataFrame:
    """Profil de toutes les colonnes, une ligne par colonne."""
    dtypes = dtypes if dtypes is not None else pd.Series(dtype=str)
    rows = [profile_column(data[c], str(dtypes.get(c, ""))) for c in data.columns]
    return pd.DataFrame(rows)


def modality_breakdown(
    values: pd.Series, max_modalities: int = _MAX_MODALITIES
) -> pd.DataFrame | None:
    """Inventaire **exhaustif** des modalités d'une colonne, ou `None` si trop nombreuses.

    Une modalité est une valeur **normalisée** (casse, accents et espaces
    neutralisés) : c'est l'unité que compte `n_distinct_normalise`. La colonne
    `ecritures` en donne les orthographes réellement rencontrées, et c'est là que
    se lisent les décisions à prendre — « f » et « femme » sont deux écritures de
    deux modalités distinctes, les rapprocher est un recodage qui se décide.

    Rendu : une ligne par modalité (`modalite`, `n`, `part_%`, `ecritures`), la
    plus fréquente d'abord. `part_%` se rapporte aux valeurs **renseignées**, la
    part de manquants étant déjà mesurée par ailleurs (`null_%`).
    """
    filled = _filled(values)
    keys = cleaning.normalize_text(filled)
    if filled.empty or keys.nunique() > max_modalities:
        return None

    grouped = filled.groupby(keys, sort=False)
    counts = grouped.size()
    return (
        pd.DataFrame(
            {
                "n": counts,
                "part_%": (100 * counts / len(filled)).round(2),
                "ecritures": grouped.unique().map(sorted),
            }
        )
        .sort_values("n", ascending=False)
        .rename_axis("modalite")
        .reset_index()
    )


def pattern_breakdown(values: pd.Series, max_patterns: int = _MAX_PATTERNS) -> pd.DataFrame | None:
    """Inventaire des **motifs d'écriture** d'une colonne, ou `None` s'ils sont trop nombreux.

    Le pendant de `modality_breakdown` pour la forme : l'un dit ce que la colonne
    *contient*, l'autre *comment c'est écrit*. Chaque motif vient avec son
    effectif et un **exemple réel** — c'est l'exemple qui le rend lisible,
    `\\d{2}\\.\\d` ne parlant à personne pris seul.

    Il corrige surtout une lecture trompeuse du profil chiffré, qui ne retient que
    le motif dominant et sa couverture : une couverture de 33 % laisse croire que
    les deux tiers des valeurs sont mal écrites, alors que les deux premiers
    motifs peuvent n'être que le même nombre à un chiffre près (`5.5` et `18.8`).

    Rendu : une ligne par motif (`motif`, `n`, `part_%`, `exemple`), le plus
    fréquent d'abord. `part_%` se rapporte aux valeurs **renseignées**.
    """
    filled = _filled(values)
    if filled.empty:
        return None

    patterns = filled.map(generalize_pattern)
    counts = patterns.value_counts()
    if len(counts) > max_patterns:
        return None

    # Tri explicite : assembler des `Series` d'index identiques mais d'ordres
    # différents les réaligne sur un index trié, et l'ordre de fréquence serait perdu.
    return (
        pd.DataFrame(
            {
                "n": counts,
                "part_%": (100 * counts / len(filled)).round(2),
                "exemple": filled.groupby(patterns).first(),
            }
        )
        .sort_values("n", ascending=False)
        .rename_axis("motif")
        .reset_index()
    )


def profile_csv(
    path: Path,
    report_dir: Path | None = None,
    max_modalities: int = _MAX_MODALITIES,
) -> CsvProfile:
    """Profile un CSV de bout en bout : le fichier, ses colonnes, ses valeurs en texte.

    `report_dir` déclenche l'écriture d'un **rapport HTML** complet dans ce dossier
    (un fichier par CSV, chemin rendu dans `CsvProfile.report_path`) : les quatorze
    indicateurs, et l'inventaire exhaustif des modalités de toute colonne qui en
    compte au plus `max_modalities`. Laissé à `None` — le défaut — rien n'est
    écrit : mesurer ne touche pas au disque tant qu'on ne l'a pas demandé.
    """
    data, file_profile = read_as_text(path)
    dtypes = read_inferred_dtypes(path, file_profile)
    profile = CsvProfile(file=file_profile, columns=profile_columns(data, dtypes), data=data)
    if report_dir is None:
        return profile

    breakdowns = {
        str(column): modality_breakdown(data[column], max_modalities) for column in data.columns
    }
    patterns = {str(column): pattern_breakdown(data[column]) for column in data.columns}
    return replace(
        profile, report_path=profiling_report.write(profile, breakdowns, patterns, report_dir)
    )
