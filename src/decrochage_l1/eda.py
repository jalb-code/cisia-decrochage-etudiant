"""Analyse exploratoire — mesurer, et savoir distinguer une mesure de son bruit.

Le module ne décide rien : il **mesure**. Chaque fonction rend un `DataFrame` ou un
scalaire que le notebook affiche tel quel ; l'interprétation et la décision vivent
dans le notebook, section par section.

Deux familles, séparées dans le fichier :

- **Mesure** — équilibre des classes, profils numériques, modalités, manquants,
  valeurs extrêmes, associations ;
- **Tracé** — enveloppes minces autour de matplotlib, sans aucun calcul : une
  grille de panneaux, et les formes qu'appelle une exploration (histogramme,
  boîte à moustaches, barres simples ou groupées, carte de chaleur, valeur dans
  sa bande de bruit, occupation d'un domaine). Le style tient dans `set_style`,
  la palette dans `PALETTE`.

Un tracé **porte ses chiffres** dès qu'il peut (`labels`, `annotations`) : c'est
ce qui lui permet de remplacer le tableau en regard plutôt que de le doubler. Une
figure se relit d'un coup d'œil, deux sorties qui se répètent ne se lisent pas.

Quatre partis pris traversent les mesures.

- **Un manquant est une modalité** dès qu'on croise deux variables catégorielles.
  L'absence d'information est elle-même une information ; l'écarter du tableau de
  contingence ferait disparaître ce qu'on cherche justement à voir.
- **Une association se lit contre son bruit.** Sur 5 200 lignes, un V de Cramér de
  0,04 n'est pas « faible » : c'est peut-être exactement ce que produit le hasard.
  Chaque mesure d'association est donc rendue avec deux étalons calculés par
  **permutation** à graine fixée — un plafond de bruit (`bruit_95`, lisible dans
  l'unité de la mesure) et une **p-valeur empirique** (`p_permutation`). La
  p-valeur, et non un verdict binaire : à 95 %, une variable indépendante sur
  vingt franchit le plafond, et une section qui teste dix variables en verrait
  passer une pour de bon.
- **Une borne de domaine se déclare, elle ne se déduit pas** — et le module la
  reçoit, il ne la porte pas. L'écart interquartile dit ce qui est *rare*, le
  domaine seul dit ce qui est *faux* : confondre les deux ferait passer une note
  de 19,9/20 pour une anomalie.
- **Un attendu vaut mieux qu'un seuil.** Plutôt que de décréter qu'une
  co-occurrence de manquants est « forte », `missing_per_row` confronte la
  distribution observée à celle qu'on aurait si les colonnes manquaient
  indépendamment les unes des autres.

Les colonnes des `DataFrame` rendus sont nommées en français : ce sont des sorties
de notebook, lues par un jury, pas des structures internes.
"""

import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.figure import Figure

# Étiquette des valeurs absentes quand elles entrent dans un tableau de
# contingence — cf. le premier parti pris du module.
MISSING_LABEL = "(manquant)"

# Multiplicateur de l'écart interquartile (règle de Tukey). 1,5 est la convention ;
# le paramètre reste exposé parce que le choix se défend, il ne se subit pas.
IQR_K = 1.5

# Palette : instance de référence du référentiel de visualisation, validée pour la
# vision des couleurs (écart adjacent CVD ΔE 9,1 en mode clair). Le notebook est
# lu et imprimé en clair : un seul mode est assumé.
PALETTE: dict[str, str] = {
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "ink_secondary": "#52514e",
    "muted": "#898781",  # graduations et étiquettes d'axe
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "series_1": "#2a78d6",  # bleu
    "series_2": "#eb6834",  # orange
    "series_3": "#1baf7a",  # aqua
    "wash": "#cde2fb",  # bleu très clair : fond d'un intervalle, jamais une série
}

# Deux échelles continues, et deux seulement. Divergente (bleu ↔ gris ↔ rouge) pour
# une grandeur signée : le gris central doit se lire « rien ». Séquentielle (bleu
# clair → foncé) pour une grandeur positive — une seule teinte, jamais d'arc-en-ciel.
DIVERGING = LinearSegmentedColormap.from_list("decrochage_div", ["#2a78d6", "#f0efec", "#e34948"])
SEQUENTIAL = LinearSegmentedColormap.from_list(
    "decrochage_seq", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
)


def set_style() -> None:
    """Applique le style des figures — marques fines, grille en retrait, sans cadre.

    Appelée une fois en préambule de section. Tout ce qui est décoratif est mis en
    retrait pour que la donnée porte l'encre : grille d'un ton au-dessus du fond,
    axes en gris, aucune bordure de légende.
    """
    plt.rcParams.update(
        {
            "figure.dpi": 110,
            "figure.facecolor": PALETTE["surface"],
            "axes.facecolor": PALETTE["surface"],
            "axes.edgecolor": PALETTE["axis"],
            "axes.labelcolor": PALETTE["ink_secondary"],
            "axes.titlecolor": PALETTE["ink"],
            "axes.titlesize": 8.5,
            "axes.labelsize": 8,
            "axes.grid": True,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.color": PALETTE["grid"],
            "grid.linewidth": 0.6,
            "xtick.color": PALETTE["muted"],
            "ytick.color": PALETTE["muted"],
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "font.size": 8,
            "font.sans-serif": ["Segoe UI", "DejaVu Sans", "sans-serif"],
            "legend.frameon": False,
            "legend.fontsize": 7.5,
            "lines.linewidth": 1.6,
        }
    )


def as_float(data: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """Convertit les types numériques *nullable* de pandas en `float64`.

    Les colonnes produites par la conformation sont en `Int64` / `Float64` — les
    manquants y sont représentés par `pd.NA`, que ni numpy ni matplotlib ne savent
    lire. La conversion les ramène à `NaN`, sans quoi tout quantile, toute
    corrélation et tout histogramme lèverait.
    """
    return data.astype("float64")


def _as_modality(values: pd.Series) -> pd.Series:
    """Ramène une colonne à des modalités comparables, manquants compris.

    Le passage par le texte est délibéré : il met un booléen `Int64`, une chaîne et
    une catégorie sur le même plan, et donne au manquant une étiquette visible
    plutôt que de le laisser disparaître d'un décompte ou d'un tableau de
    contingence.
    """
    return values.astype("string").fillna(MISSING_LABEL)


# =============================================================================
#  MESURE — cibles et variables, une colonne à la fois
# =============================================================================


def class_balance(values: pd.Series) -> pd.DataFrame:
    """Effectif et part de chaque modalité, la plus fréquente d'abord.

    Les manquants comptent comme une modalité : sur une cible, une valeur absente
    est une ligne inapprenable, et ne pas la voir serait le pire des silences.
    """
    counts = _as_modality(values).value_counts(dropna=False)
    return pd.DataFrame(
        {
            "modalite": counts.index.astype(str),
            "n": counts.to_numpy(),
            "part_%": (100 * counts / len(values)).round(2).to_numpy(),
        }
    )


def imbalance_ratio(values: pd.Series) -> float:
    """Rapport de la modalité majoritaire à la minoritaire — le déséquilibre en un chiffre.

    Deux classes équilibrées rendent 1,0. C'est ce rapport, non la prévalence, qui
    dit combien la classe rare est écrasée dans une fonction de coût.
    """
    counts = _as_modality(values).value_counts()
    return float(counts.iloc[0] / counts.iloc[-1]) if len(counts) > 1 else 1.0


def numeric_overview(data: pd.DataFrame) -> pd.DataFrame:
    """Profil de forme des colonnes numériques : centre, dispersion, bornes, asymétrie.

    `describe` de pandas s'arrête à la dispersion ; l'asymétrie est ajoutée parce
    qu'elle est ce qui décide de la lecture d'une moyenne. À 1,5 d'asymétrie, la
    moyenne n'est plus le centre de rien.

    Aucune part de manquants ici : `n_renseigne` la porte déjà, et le sujet
    appartient à la mesure des valeurs absentes (`missing_overview`).
    """
    numbers = as_float(data)
    return pd.DataFrame(
        {
            "colonne": numbers.columns,
            "n_renseigne": numbers.notna().sum().to_numpy(),
            "moyenne": numbers.mean().round(2).to_numpy(),
            "ecart_type": numbers.std().round(2).to_numpy(),
            "min": numbers.min().round(2).to_numpy(),
            "q1": numbers.quantile(0.25).round(2).to_numpy(),
            "mediane": numbers.median().round(2).to_numpy(),
            "q3": numbers.quantile(0.75).round(2).to_numpy(),
            "max": numbers.max().round(2).to_numpy(),
            "asymetrie": numbers.skew().round(2).to_numpy(),
        }
    )


def modality_counts(values: pd.Series) -> pd.Series:
    """Effectif de chaque modalité, croissant, manquants compris — de quoi tracer des barres."""
    return _as_modality(values).value_counts().sort_values()


def modality_overview(data: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Inventaire resserré des colonnes catégorielles : combien de modalités, et lesquelles pèsent.

    Une ligne par colonne — la dominante et la plus rare avec leurs parts. C'est le
    couple qui se lit : une dominante à 99 % dit une colonne sans variance, une plus
    rare à 0,6 % dit une modalité que le découpage train / test peut faire disparaître.
    """
    rows = []
    for column in columns if columns is not None else list(data.columns):
        filled = data[column].dropna()
        parts = 100 * filled.value_counts(normalize=True)
        rows.append(
            {
                "colonne": column,
                "n_modalites": int(filled.nunique()),
                "dominante": str(parts.index[0]),
                "part_dominante_%": round(float(parts.iloc[0]), 2),
                "plus_rare": str(parts.index[-1]),
                "part_rare_%": round(float(parts.iloc[-1]), 2),
                "manquants_%": round(100 * data[column].isna().mean(), 2),
            }
        )
    return pd.DataFrame(rows)


def rare_modalities(
    data: pd.DataFrame, columns: list[str] | None = None, max_share: float = 0.01
) -> pd.DataFrame:
    """Modalités dont la part des valeurs renseignées reste sous `max_share`.

    Elles importent pour deux raisons sans rapport : un encodage appris sur le
    train seul peut ne jamais les rencontrer, et un audit d'équité ne peut rien
    conclure d'un effectif de trente personnes. Les nommer maintenant évite de les
    découvrir en §9.
    """
    rows = []
    for column in columns if columns is not None else list(data.columns):
        filled = data[column].dropna()
        parts = filled.value_counts(normalize=True)
        for modality, part in parts[parts < max_share].items():
            rows.append(
                {
                    "colonne": column,
                    "modalite": str(modality),
                    "n": int((filled == modality).sum()),
                    "part_%": round(100 * float(part), 2),
                }
            )
    return pd.DataFrame(rows, columns=["colonne", "modalite", "n", "part_%"])


def quasi_constant(data: pd.DataFrame, min_share: float = 0.95) -> pd.DataFrame:
    """Colonnes dont une seule valeur couvre au moins `min_share` des lignes renseignées.

    Le seuil est strictement en dessous de 1 : une colonne à 99,9 % identique n'a
    pas plus d'information qu'une constante, mais aucun test d'égalité ne la
    signalerait.
    """
    rows = []
    for column in data.columns:
        filled = data[column].dropna()
        if filled.empty:
            continue
        parts = filled.value_counts(normalize=True)
        if float(parts.iloc[0]) >= min_share:
            rows.append(
                {
                    "colonne": column,
                    "dominante": str(parts.index[0]),
                    "part_%": round(100 * float(parts.iloc[0]), 2),
                }
            )
    return pd.DataFrame(rows, columns=["colonne", "dominante", "part_%"])


# =============================================================================
#  MESURE — valeurs manquantes
# =============================================================================


def missing_overview(data: pd.DataFrame, themes: dict[str, str] | None = None) -> pd.DataFrame:
    """Colonnes porteuses de manquants, de la plus trouée à la moins.

    `themes` — colonne vers famille métier — rattache chaque colonne à son thème :
    c'est le regroupement qui montre si les trous frappent un thème entier ou se
    dispersent.
    """
    missing = data.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    frame = pd.DataFrame(
        {
            "colonne": missing.index,
            "n_manquants": missing.to_numpy(),
            "part_%": (100 * missing / len(data)).round(2).to_numpy(),
        }
    )
    if themes is not None:
        frame["theme"] = frame["colonne"].map(themes)
    return frame


def _poisson_binomial(rates: np.ndarray) -> np.ndarray:
    """Loi du nombre de manquants par ligne **si les colonnes manquaient indépendamment**.

    Convolution exacte, colonne par colonne : chacune ajoute un manquant avec sa
    probabilité propre. C'est l'attendu contre lequel se lit l'observé — pas une
    approximation de Poisson, qui supposerait des taux égaux.
    """
    distribution = np.array([1.0])
    for rate in rates:
        shifted = np.zeros(len(distribution) + 1)
        shifted[:-1] += distribution * (1 - rate)
        shifted[1:] += distribution * rate
        distribution = shifted
    return distribution


def missing_per_row(data: pd.DataFrame) -> pd.DataFrame:
    """Lignes par nombre de colonnes manquantes — observé face à l'attendu sous indépendance.

    La question que le tableau tranche : les trous se **concentrent**-ils sur
    quelques dossiers, ou se répartissent-ils ? Un observé qui suit l'attendu dit
    que les colonnes manquent sans se donner rendez-vous ; un excès aux deux
    extrémités (beaucoup de lignes complètes *et* beaucoup de lignes très trouées)
    dit l'inverse, et fait de la complétude une variable en soi.
    """
    rates = data.isna().mean()
    rates = rates[rates > 0]
    observed = data.isna().sum(axis=1).value_counts()
    expected = _poisson_binomial(rates.to_numpy()) * len(data)

    frame = pd.DataFrame(
        {
            "nb_colonnes_manquantes": np.arange(len(expected)),
            "n_lignes_observe": [int(observed.get(k, 0)) for k in range(len(expected))],
            "n_lignes_attendu": np.round(expected).astype(int),
        }
    )
    # Au-delà du dernier cas observé, l'attendu tombe sous la ligne : ne pas
    # dérouler une queue de zéros qui n'apprend rien.
    keep = (frame["n_lignes_observe"] > 0) | (frame["n_lignes_attendu"] > 0)
    return frame[keep].reset_index(drop=True)


def missing_vs_target(
    data: pd.DataFrame,
    target: pd.Series,
    n_permutations: int = 500,
    random_state: int = 0,
) -> pd.DataFrame:
    """Taux d'une cible **binaire** selon que chaque colonne est manquante ou renseignée.

    C'est le test qui sépare deux mécanismes aux conséquences opposées : un écart
    nul dit une absence sans rapport avec l'issue (imputable sans biais), un écart
    marqué dit que **manquer est informatif** — et qu'imputer effacerait ce signal
    au lieu de le combler.

    L'écart brut ne suffit pas à trancher : sur 624 lignes manquantes contre 4 576,
    quelques points d'écart sont dans le bruit d'échantillonnage. Les deux dernières
    colonnes le disent — plafond de bruit et p-valeur, par permutation de
    l'indicateur de manquant, tous deux en points de pourcentage comme `ecart_pt`.
    """
    rows = []
    for column in data.columns:
        missing = data[column].isna()
        if not missing.any() or missing.all():
            continue
        when_missing = 100 * float(as_float(target[missing]).mean())
        when_present = 100 * float(as_float(target[~missing]).mean())
        observed = group_spread(target, missing)
        draws = _spread_draws(target, missing, n_permutations, random_state)
        ceiling, p_value = _permutation_summary(observed, draws)
        rows.append(
            {
                "colonne": column,
                "n_manquants": int(missing.sum()),
                "taux_si_manquant_%": round(when_missing, 2),
                "taux_si_present_%": round(when_present, 2),
                "ecart_pt": round(when_missing - when_present, 2),
                "bruit_95_pt": round(100 * ceiling, 2),
                "p_permutation": round(p_value, 4),
            }
        )
    frame = pd.DataFrame(
        rows,
        columns=[
            "colonne",
            "n_manquants",
            "taux_si_manquant_%",
            "taux_si_present_%",
            "ecart_pt",
            "bruit_95_pt",
            "p_permutation",
        ],
    )
    return frame.sort_values("ecart_pt", key=abs, ascending=False, ignore_index=True)


def missing_mechanism(
    data: pd.DataFrame,
    columns: list[str] | None = None,
    n_permutations: int = 500,
    random_state: int = 0,
    quantile: float = 0.95,
) -> pd.DataFrame:
    """Pour chaque colonne trouée, la variable observée dont son ABSENCE dépend le plus.

    Le test qui commande la stratégie d'imputation : l'absence d'une colonne dépend-elle
    des autres variables observées ? Si oui, l'hypothèse MCAR - « manque au hasard,
    indépendamment de tout » - tombe. On ne départage pas MAR de MNAR, qui reste une
    hypothèse métier documentée ; on **rejette MCAR, ou non**.

    Chaque autre colonne est confrontée à l'indicateur de manquant selon sa nature :
    catégorielle par le V de Cramér, numérique par l'écart de ses moyennes entre lignes
    manquantes et renseignées (`group_spread`). Les deux mesures ne partageant pas
    d'échelle, elles ne se comparent pas entre elles : chacune est jugée contre **son
    propre** plafond de bruit par permutation, et le classement se fait sur la p-valeur.
    La ligne rend la variable la plus significative - celle qui, si elle existe, fait
    tomber MCAR. `mcar_rejete` est vrai dès que sa p-valeur passe sous `1 - quantile`.
    """
    alpha = 1 - quantile
    targets = (
        columns
        if columns is not None
        else [c for c in data.columns if data[c].isna().any() and not data[c].isna().all()]
    )
    rows = []
    for column in targets:
        indicator = data[column].isna()
        best, best_p = None, None
        for other in data.columns:
            if other == column:
                continue
            if pd.api.types.is_numeric_dtype(data[other]):
                nature = "numérique"
                observed = group_spread(data[other], indicator)
                draws = _spread_draws(data[other], indicator, n_permutations, random_state)
            else:
                nature = "catégorielle"
                observed = cramers_v(data[other], indicator)
                draws = _cramers_v_draws(data[other], indicator, n_permutations, random_state)
            ceiling, p_value = _permutation_summary(observed, draws, quantile)
            if best_p is None or p_value < best_p:
                best_p = p_value
                best = {
                    "variable_liee": other,
                    "type": nature,
                    "mesure": round(observed, 3),
                    "bruit_95": round(ceiling, 3),
                    "p_permutation": round(p_value, 4),
                }
        if best is None:  # aucune autre colonne à confronter
            continue
        rows.append({"colonne": column, **best, "mcar_rejete": bool(best_p < alpha)})
    return pd.DataFrame(
        rows,
        columns=[
            "colonne",
            "variable_liee",
            "type",
            "mesure",
            "bruit_95",
            "p_permutation",
            "mcar_rejete",
        ],
    ).sort_values("p_permutation", ignore_index=True)


# =============================================================================
#  MESURE — valeurs extrêmes
# =============================================================================


def iqr_bounds(values: pd.Series, k: float = IQR_K) -> tuple[float, float]:
    """Bornes de Tukey — `q1 - k·IQR` et `q3 + k·IQR`.

    Elles disent ce qui est **rare** dans la distribution observée, jamais ce qui
    est faux : sur une échelle bornée (une note, un accord de 1 à 5), les bornes
    peuvent tomber à l'intérieur du domaine et désigner des valeurs parfaitement
    légitimes.
    """
    numbers = as_float(values).dropna()
    q1, q3 = float(numbers.quantile(0.25)), float(numbers.quantile(0.75))
    return q1 - k * (q3 - q1), q3 + k * (q3 - q1)


def _format_range(low: float, high: float) -> str:
    """Écrit un intervalle de domaine en notation d'intervalle, l'infini compris.

    Un plafond infini rend un intervalle ouvert (`[0 ; ∞[`) : c'est la façon
    d'écrire « le métier ne borne pas » sans avancer de valeur.
    """
    return f"[{low:g} ; ∞[" if math.isinf(high) else f"[{low:g} ; {high:g}]"


def domain_check(data: pd.DataFrame, ranges: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Bornes observées face au domaine déclaré, et part du domaine réellement occupée.

    Le contrôle qui convient aux variables que le métier **borne** (une note, un
    pourcentage, une échelle d'accord) : leurs extrémités suffisent à répondre, et
    l'écart interquartile n'a rien à y faire - sur une échelle 1-5 de médiane 3,
    il déclarerait aberrante la réponse « 1 ».

    `debut_%` et `fin_%` situent les valeurs observées dans le domaine, 0 % étant
    la borne basse et 100 % la borne haute. Ils ne sont **pas** ramenés dans
    l'intervalle : une valeur hors domaine doit sortir du cadre, c'est le but. Ils
    disent aussi la part de l'échelle réellement utilisée - une variable qui
    n'occupe qu'un dixième de son domaine signale une borne déclarée trop large.

    Les colonnes sans plafond fini sont ignorées : leur position relative n'aurait
    pas de sens.
    """
    numbers = as_float(data)
    rows = []
    for column in numbers.columns:
        declared = ranges.get(str(column))
        if declared is None or not math.isfinite(declared[1]):
            continue
        floor, ceiling = declared
        values = numbers[column].dropna()
        span = ceiling - floor
        rows.append(
            {
                "colonne": column,
                "domaine": _format_range(floor, ceiling),
                "min": round(float(values.min()), 2),
                "max": round(float(values.max()), 2),
                "n_hors_domaine": int(((values < floor) | (values > ceiling)).sum()),
                "debut_%": round(100 * (float(values.min()) - floor) / span, 1),
                "fin_%": round(100 * (float(values.max()) - floor) / span, 1),
            }
        )
    return pd.DataFrame(rows)


def iqr_mask(data: pd.DataFrame, k: float = IQR_K) -> pd.DataFrame:
    """Masque booléen des valeurs hors bornes de Tukey, colonne par colonne.

    Rendu séparément du comptage parce qu'il répond à une autre question : non pas
    « combien de valeurs », mais **combien de lignes** en portent au moins une.
    """
    numbers = as_float(data)
    flagged = {}
    for column in numbers.columns:
        low, high = iqr_bounds(numbers[column], k)
        flagged[column] = (numbers[column] < low) | (numbers[column] > high)
    return pd.DataFrame(flagged, index=data.index).fillna(False)


def iqr_outliers(data: pd.DataFrame, k: float = IQR_K) -> pd.DataFrame:
    """Valeurs rares au sens de Tukey, pour les variables qu'aucun plafond métier ne borne.

    Ce que la mesure dit et ne dit pas : elle désigne ce qui est **rare dans la
    distribution observée**, jamais ce qui est faux. Le jugement de plausibilité
    reste à faire, et il se lit mieux sur une boîte à moustaches - une queue
    continue n'est pas une poignée de points isolés.
    """
    numbers = as_float(data)
    flagged = iqr_mask(data, k)
    rows = []
    for column in numbers.columns:
        values = numbers[column].dropna()
        low, high = iqr_bounds(values, k)
        rows.append(
            {
                "colonne": column,
                "min": round(float(values.min()), 2),
                "max": round(float(values.max()), 2),
                "borne_basse": round(low, 2),
                "borne_haute": round(high, 2),
                "n_hors_iqr": int(flagged[column].sum()),
                "part_%": round(100 * float(flagged[column].sum()) / len(values), 2),
            }
        )
    return pd.DataFrame(rows).sort_values("part_%", ascending=False, ignore_index=True)


# =============================================================================
#  MESURE — associations
# =============================================================================


def matrix_pairs(
    matrix: pd.DataFrame, threshold: float = 0.0, name: str = "valeur"
) -> pd.DataFrame:
    """Paires du triangle supérieur d'une matrice carrée, la plus forte en valeur absolue d'abord.

    Ne rend que le triangle supérieur : une matrice symétrique porte chaque paire
    deux fois, ce qui est juste pour l'œil et faux pour une liste. Le tri sur la
    valeur absolue est ce qui empêche une redondance **négative** d'être reléguée
    en fin de tableau par son signe.
    """
    upper = np.triu(np.ones(matrix.shape, dtype=bool), k=1)
    pairs = matrix.where(upper).stack().dropna()
    pairs = pairs[pairs.abs() >= threshold].sort_values(key=abs, ascending=False)
    frame = pairs.round(3).rename(name).reset_index()
    return frame.set_axis(["variable_1", "variable_2", name], axis=1)


def correlation_pairs(
    data: pd.DataFrame, method: str = "spearman", threshold: float = 0.0
) -> pd.DataFrame:
    """Paires de colonnes numériques dont `|corrélation| ≥ threshold`, la plus forte d'abord."""
    return matrix_pairs(as_float(data).corr(method=method), threshold, "correlation")


def _codes(values: pd.Series) -> tuple[np.ndarray, int]:
    """Modalités encodées en entiers consécutifs, et leur nombre."""
    codes, uniques = pd.factorize(_as_modality(values), use_na_sentinel=False)
    return codes, len(uniques)


def _counts(left: np.ndarray, right: np.ndarray, n_left: int, n_right: int) -> np.ndarray:
    """Tableau de contingence à partir de codes — un `bincount` plutôt qu'un `crosstab`.

    La forme compte : le test par permutation reconstruit ce tableau des centaines
    de fois, et un `crosstab` y coûterait deux ordres de grandeur de plus.
    """
    flat = np.bincount(left * n_right + right, minlength=n_left * n_right)
    return flat.reshape(n_left, n_right).astype("float64")


def _v_from_counts(observed: np.ndarray) -> float:
    """V de Cramér à partir d'un tableau de contingence."""
    total = observed.sum()
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / total
    chi2 = np.divide(
        (observed - expected) ** 2, expected, out=np.zeros_like(observed), where=expected > 0
    ).sum()
    return float(np.sqrt(chi2 / total / (min(observed.shape) - 1)))


def cramers_v(left: pd.Series, right: pd.Series) -> float:
    """Force d'association entre deux variables catégorielles, entre 0 et 1.

    Le pendant catégoriel d'une corrélation : symétrique, sans direction, et
    indifférent à l'ordre des modalités — c'est ce qui le rend lisible sur
    `filiere` comme sur `couleur_carte_etudiante`.

    Rend 0 pour une colonne constante, où aucune association n'est définissable.
    À lire contre `cramers_v_noise` : la mesure est biaisée vers le haut, d'autant
    plus que les modalités sont nombreuses.
    """
    left_codes, n_left = _codes(left)
    right_codes, n_right = _codes(right)
    if min(n_left, n_right) < 2:
        return 0.0
    return _v_from_counts(_counts(left_codes, right_codes, n_left, n_right))


def _permutation_summary(
    observed: float, draws: np.ndarray, quantile: float = 0.95
) -> tuple[float, float]:
    """Plafond de bruit et p-valeur empirique, à partir des tirages permutés d'une statistique.

    La p-valeur compte les tirages qui atteignent l'observé, **plus un** au
    numérateur comme au dénominateur : sans cette correction, une statistique
    qu'aucune permutation n'égale rendrait `p = 0`, ce qui affirme plus qu'un
    nombre fini de tirages ne permet de savoir. Le plancher vaut donc
    `1 / (n + 1)`.
    """
    ceiling = float(np.quantile(draws, quantile))
    p_value = float((1 + int((draws >= observed).sum())) / (1 + len(draws)))
    return ceiling, p_value


def _cramers_v_draws(
    left: pd.Series, right: pd.Series, n_permutations: int, random_state: int
) -> np.ndarray:
    """Tirages du V de Cramér sous permutation de `right` : le lien détruit, effectifs intacts."""
    left_codes, n_left = _codes(left)
    right_codes, n_right = _codes(right)
    if min(n_left, n_right) < 2:
        return np.zeros(n_permutations)
    generator = np.random.default_rng(random_state)
    return np.array(
        [
            _v_from_counts(_counts(left_codes, generator.permutation(right_codes), n_left, n_right))
            for _ in range(n_permutations)
        ]
    )


def cramers_v_noise(
    left: pd.Series,
    right: pd.Series,
    n_permutations: int = 500,
    random_state: int = 0,
    quantile: float = 0.95,
) -> float:
    """Plafond de bruit du V de Cramér — son quantile sous permutation de `right`.

    Permuter une colonne détruit son lien avec l'autre sans toucher à ses
    effectifs : ce que le V vaut encore après permutation est ce que le hasard
    produit à cette taille d'échantillon et à ce nombre de modalités. Un V observé
    sous ce plafond n'est pas « faible », il est **indiscernable du hasard** — la
    seule formulation qu'on puisse défendre.

    La graine est fixée : deux exécutions du notebook rendent le même plafond.
    """
    return float(np.quantile(_cramers_v_draws(left, right, n_permutations, random_state), quantile))


def cramers_v_matrix(data: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Matrice des V de Cramér entre colonnes catégorielles — symétrique, diagonale à 1."""
    names = list(columns if columns is not None else data.columns)
    matrix = pd.DataFrame(1.0, index=names, columns=names)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            matrix.loc[first, second] = matrix.loc[second, first] = round(
                cramers_v(data[first], data[second]), 3
            )
    return matrix


def categorical_association(
    data: pd.DataFrame,
    columns: list[str],
    target: pd.Series,
    n_permutations: int = 500,
    random_state: int = 0,
) -> pd.DataFrame:
    """Association de chaque colonne catégorielle à la cible, avec ses deux étalons de bruit.

    `n_groupes` compte les modalités **telles que la mesure les a vues**, un
    manquant compris : c'est ce qui explique qu'une colonne à 19 libellés en
    déclare 20 ici.
    """
    rows = []
    for column in columns:
        observed = cramers_v(data[column], target)
        draws = _cramers_v_draws(data[column], target, n_permutations, random_state)
        ceiling, p_value = _permutation_summary(observed, draws)
        rows.append(
            {
                "colonne": column,
                "n_groupes": int(_as_modality(data[column]).nunique()),
                "v_cramer": round(observed, 3),
                "bruit_95": round(ceiling, 3),
                "p_permutation": round(p_value, 4),
            }
        )
    return pd.DataFrame(rows).sort_values("v_cramer", ascending=False, ignore_index=True)


def _spread_from_codes(numbers: np.ndarray, codes: np.ndarray, n_groups: int) -> float:
    """Étendue des moyennes par groupe, à partir de codes — la forme que la permutation rejoue."""
    valid = ~np.isnan(numbers)
    sums = np.bincount(codes[valid], weights=numbers[valid], minlength=n_groups)
    counts = np.bincount(codes[valid], minlength=n_groups)
    means = sums / np.where(counts == 0, np.nan, counts)
    return float(np.nanmax(means) - np.nanmin(means))


def group_spread(values: pd.Series, groups: pd.Series) -> float:
    """Écart entre la plus haute et la plus basse moyenne de `values` par modalité de `groups`.

    Mesure ce que le V de Cramér ne sait pas dire : l'association d'une variable
    catégorielle à une grandeur **continue**. Et elle a l'avantage de s'exprimer
    dans l'unité de la cible — « 0,6 point de moyenne finale » se discute avec un
    responsable pédagogique, un V de 0,04 non.
    """
    codes, n_groups = _codes(groups)
    return _spread_from_codes(as_float(values).to_numpy(), codes, n_groups)


def _spread_draws(
    values: pd.Series, groups: pd.Series, n_permutations: int, random_state: int
) -> np.ndarray:
    """Tirages de `group_spread` sous permutation des groupes — effectifs de groupe intacts."""
    codes, n_groups = _codes(groups)
    numbers = as_float(values).to_numpy()
    generator = np.random.default_rng(random_state)
    return np.array(
        [
            _spread_from_codes(numbers, generator.permutation(codes), n_groups)
            for _ in range(n_permutations)
        ]
    )


def group_spread_noise(
    values: pd.Series,
    groups: pd.Series,
    n_permutations: int = 500,
    random_state: int = 0,
    quantile: float = 0.95,
) -> float:
    """Plafond de bruit de `group_spread` — son quantile sous permutation des groupes.

    Même raisonnement que `cramers_v_noise`, et même nécessité : plus une variable
    a de modalités et plus certaines sont peu peuplées, plus le hasard écarte
    naturellement les moyennes. Sans cet étalon, un écart de cinq points sur huit
    groupes passerait pour un effet.
    """
    return float(np.quantile(_spread_draws(values, groups, n_permutations, random_state), quantile))


def group_spread_table(
    data: pd.DataFrame,
    columns: list[str],
    targets: dict[str, pd.Series],
    n_permutations: int = 500,
    random_state: int = 0,
) -> pd.DataFrame:
    """Écart entre modalités, plafond de bruit et p-valeur, pour chaque colonne et chaque cible.

    Un tableau et non deux : les deux cibles se lisent l'une sous l'autre pour la
    même variable, ce qui évite de conclure d'une seule qu'une variable ne porte
    rien. Les valeurs sont dans l'unité de la cible passée — le notebook décide
    donc s'il transmet un taux (en points de pourcentage) ou une note.
    """
    rows = []
    for column in columns:
        for name, target in targets.items():
            observed = group_spread(target, data[column])
            draws = _spread_draws(target, data[column], n_permutations, random_state)
            ceiling, p_value = _permutation_summary(observed, draws)
            rows.append(
                {
                    "colonne": column,
                    "cible": name,
                    "n_groupes": int(_as_modality(data[column]).nunique()),
                    "ecart_observe": round(observed, 3),
                    "bruit_95": round(ceiling, 3),
                    "p_permutation": round(p_value, 4),
                }
            )
    return pd.DataFrame(rows)


def target_rate_by_modality(
    data: pd.DataFrame, column: str, target: pd.Series, order: str = "modalite"
) -> pd.DataFrame:
    """Taux moyen de la cible pour chaque modalité d'une colonne, avec son effectif.

    L'effectif est indissociable du taux : un écart de dix points sur trente
    personnes ne dit rien, le même sur mille dit tout. Les manquants forment une
    modalité à part entière — c'est la seule façon de voir si l'absence de réponse
    va de pair avec l'issue.
    """
    modalities = _as_modality(data[column]).rename("modalite")
    grouped = as_float(target).groupby(modalities, observed=True)
    frame = pd.DataFrame({"n": grouped.size(), "taux_%": (100 * grouped.mean()).round(2)})
    return frame.reset_index().sort_values(order, ignore_index=True)


# =============================================================================
#  TRACÉ — enveloppes minces, aucun calcul
# =============================================================================


def panels(
    n: int, n_cols: int = 4, size: tuple[float, float] = (3.1, 2.2)
) -> tuple[Figure, np.ndarray]:
    """Grille de `n` panneaux, les cases excédentaires masquées.

    La largeur s'ajuste au contenu : trois panneaux demandés sur quatre colonnes
    rendent une figure de trois colonnes, non une case vide au bout de la rangée.
    """
    n_cols = min(n_cols, max(n, 1))
    n_rows = math.ceil(n / n_cols)
    figure, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * size[0], n_rows * size[1]))
    flat = np.atleast_1d(axes).ravel()
    for axis in flat[n:]:
        axis.set_visible(False)
    return figure, flat[:n]


def _bins_for(values: pd.Series, bins: int) -> int:
    """Nombre de classes d'un histogramme, plafonné aux valeurs distinctes.

    Sans ce plafond, une colonne à trois valeurs (`nb_ue_total`) rendrait trente
    classes dont vingt-sept vides — un peigne illisible au lieu de trois barres.
    """
    return int(min(bins, max(values.nunique(), 1)))


def plot_histograms(data: pd.DataFrame, n_cols: int = 4, bins: int = 30) -> Figure:
    """Un histogramme par colonne numérique."""
    numbers = as_float(data)
    figure, axes = panels(numbers.shape[1], n_cols)
    for axis, column in zip(axes, numbers.columns, strict=True):
        values = numbers[column].dropna()
        axis.hist(values, bins=_bins_for(values, bins), color=PALETTE["series_1"], linewidth=0)
        axis.set_title(str(column))
        axis.grid(axis="x", visible=False)
    figure.tight_layout()
    return figure


def plot_boxplots(
    data: pd.DataFrame, n_cols: int = 4, annotations: dict[str, str] | None = None
) -> Figure:
    """Une boîte à moustaches horizontale par colonne numérique, points extrêmes compris.

    `annotations` inscrit un texte dans chaque panneau (le compte de valeurs hors
    bornes, par exemple) : c'est ce qui dispense du tableau chiffré en regard.
    """
    numbers = as_float(data)
    annotations = annotations or {}
    figure, axes = panels(numbers.shape[1], n_cols, size=(3.1, 1.6))
    for axis, column in zip(axes, numbers.columns, strict=True):
        axis.boxplot(
            numbers[column].dropna(),
            orientation="horizontal",
            widths=0.45,
            patch_artist=True,
            boxprops={"facecolor": PALETTE["series_1"], "edgecolor": PALETTE["ink_secondary"]},
            medianprops={"color": PALETTE["surface"], "linewidth": 1.2},
            whiskerprops={"color": PALETTE["ink_secondary"]},
            capprops={"color": PALETTE["ink_secondary"]},
            flierprops={
                "marker": "o",
                "markersize": 3,
                "markerfacecolor": PALETTE["series_2"],
                "markeredgecolor": "none",
                "alpha": 0.45,
            },
        )
        axis.set_title(str(column))
        axis.set_yticks([])
        axis.grid(axis="y", visible=False)
        if str(column) in annotations:
            axis.text(
                0.98,
                0.06,
                annotations[str(column)],
                transform=axis.transAxes,
                ha="right",
                va="bottom",
                fontsize=6.5,
                color=PALETTE["ink_secondary"],
            )
    figure.tight_layout()
    return figure


def _written(value: float, template: str) -> str:
    """Écrit un nombre au gabarit demandé, séparateur de milliers à la française.

    Le point décimal reste celui de Python ; seule la virgule des milliers devient
    une espace, comme le fait déjà `FileProfile.to_frame`. Aucun de ces gabarits
    n'emploie la virgule autrement.
    """
    return template.format(value).replace(",", " ")


def _label_bars(
    axis: Axes, numbers: np.ndarray, template: str, offset: float, column: float | None = None
) -> None:
    """Inscrit sa valeur pour chaque barre — c'est elle qui dispense du tableau chiffré.

    `column` aligne toutes les valeurs sur une même abscisse, à droite du cadre.
    C'est ce qu'il faut dès que l'échelle est partagée : au bout de la barre, une
    étiquette tombe sur le trait de référence, qui est justement là où les valeurs
    se pressent.
    """
    for position, value in enumerate(numbers):
        at_end = value + (offset if value >= 0 else -offset)
        axis.text(
            at_end if column is None else column,
            position,
            _written(value, template),
            ha="left" if column is not None or value >= 0 else "right",
            va="center",
            fontsize=6.5,
            color=PALETTE["ink_secondary"],
        )


def plot_bars(
    series_by_panel: dict[str, pd.Series],
    reference: float | None = None,
    n_cols: int = 4,
    shared_scale: bool = True,
    size: tuple[float, float] = (3.1, 2.0),
    labels: str | None = None,
) -> Figure:
    """Barres horizontales, un panneau par `Series` — l'index étiquette, la valeur mesure.

    Une seule teinte pour toutes les barres : leur longueur porte déjà la grandeur,
    la colorer par rang la redirait deux fois.

    `shared_scale` impose la même échelle à tous les panneaux, ce qui est la seule
    façon de comparer un taux d'une variable à l'autre — sans elle, une variation
    de deux points et une de vingt occupent la même largeur. `reference` trace le
    niveau d'ensemble : c'est lui qui donne son sens à un écart. `size` suit le
    nombre d'étiquettes : dix-sept barres dans deux pouces se chevauchent.

    `labels` est un gabarit de format (`"{:.2f}"`) qui inscrit la valeur au bout de
    chaque barre. C'est ce qui **remplace** le tableau chiffré en regard : une
    figure qui porte ses nombres se relit, deux sorties qui se répètent non.
    """
    figure, axes = panels(len(series_by_panel), n_cols, size=size)
    values = pd.concat(list(series_by_panel.values())).astype("float64")
    low, high = min(0.0, float(values.min())), max(0.0, float(values.max()))

    for axis, (title, series) in zip(axes, series_by_panel.items(), strict=True):
        numbers = series.to_numpy(dtype="float64")
        axis.barh(series.index.astype(str), numbers, color=PALETTE["series_1"], height=0.7)
        if reference is not None:
            axis.axvline(
                reference, color=PALETTE["ink_secondary"], linewidth=1.0, linestyle=(0, (4, 3))
            )

        floor, ceiling = (
            (low, high)
            if shared_scale
            else (min(0.0, float(numbers.min())), max(0.0, float(numbers.max())))
        )
        span = (ceiling - floor) or 1.0
        # La place réservée aux étiquettes est prise sur l'axe, pas sur les barres :
        # sinon la valeur du maximum sortirait du cadre.
        room = 0.22 * span if labels else 0.08 * span
        axis.set_xlim(floor - (room if floor < 0 else 0), ceiling + room)
        if labels:
            _label_bars(
                axis, numbers, labels, 0.02 * span, ceiling + 0.03 * span if shared_scale else None
            )

        axis.set_title(str(title))
        axis.grid(axis="y", visible=False)
    figure.tight_layout()
    return figure


def plot_grouped_bars(
    frame: pd.DataFrame,
    labels: str | None = None,
    size: tuple[float, float] = (6.4, 3.0),
    xlabel: str = "",
) -> Figure:
    """Barres verticales groupées — une catégorie par position de l'index, une série par colonne.

    La forme qui convient à une distribution confrontée à son attendu : les deux
    séries se lisent côte à côte sur chaque valeur, et la légende porte leur
    identité (jamais la couleur seule).
    """
    figure, axis = plt.subplots(figsize=size)
    positions = np.arange(len(frame))
    width = 0.8 / frame.shape[1]
    tints = [PALETTE["series_1"], PALETTE["series_2"], PALETTE["series_3"]]

    for index, column in enumerate(frame.columns):
        numbers = frame[column].to_numpy(dtype="float64")
        offset = (index - (frame.shape[1] - 1) / 2) * width
        axis.bar(
            positions + offset,
            numbers,
            width=width * 0.88,  # l'écart entre barres voisines est du fond, pas un trait
            color=tints[index % len(tints)],
            label=str(column),
        )
        if labels:
            for position, value in zip(positions + offset, numbers, strict=True):
                axis.text(
                    position,
                    value,
                    _written(value, labels),
                    ha="center",
                    va="bottom",
                    fontsize=6.5,
                    color=PALETTE["ink_secondary"],
                )

    axis.set_xticks(positions, frame.index.astype(str))
    axis.set_xlabel(xlabel)
    axis.grid(axis="x", visible=False)
    axis.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncols=2)
    figure.tight_layout()
    return figure


def plot_intervals(
    frame: pd.DataFrame,
    value: str,
    span: str,
    reference: float = 0.0,
    labels: str | None = None,
    size: tuple[float, float] = (6.8, 3.6),
    legend: tuple[str, str] = ("plafond de bruit", "écart observé"),
) -> Figure:
    """Une valeur observée par ligne, dans la bande de bruit qui la juge.

    La forme répond d'un coup d'œil à la question qu'un tableau de six colonnes
    posait à chaque ligne : le point sort-il de sa bande ? Un point dedans est
    indiscernable du hasard ; c'est celui qui en sort qu'il faut expliquer. La
    bande est centrée sur `reference` parce que c'est l'hypothèse qu'elle
    matérialise — l'absence d'effet.
    """
    figure, axis = plt.subplots(figsize=size)
    positions = np.arange(len(frame))
    spans = frame[span].to_numpy(dtype="float64")
    values = frame[value].to_numpy(dtype="float64")

    axis.barh(
        positions,
        2 * spans,
        left=reference - spans,
        height=0.62,
        color=PALETTE["wash"],
        label=legend[0],
    )
    axis.axvline(reference, color=PALETTE["axis"], linewidth=1.0)
    axis.scatter(
        values,
        positions,
        s=30,
        color=PALETTE["series_1"],
        edgecolor=PALETTE["surface"],  # anneau de fond : la marque ne touche pas la bande
        linewidth=1.4,
        zorder=3,
        label=legend[1],
    )
    if labels:
        for position, value_at in zip(positions, values, strict=True):
            axis.text(
                max(values.max(), spans.max()) * 1.08,
                position,
                _written(value_at, labels),
                ha="left",
                va="center",
                fontsize=6.5,
                color=PALETTE["ink_secondary"],
            )

    axis.set_yticks(positions, frame.index.astype(str))
    axis.invert_yaxis()
    axis.grid(axis="y", visible=False)
    # Au-dessus du cadre, jamais dedans : sur des barres horizontales, un coin
    # « libre » est toujours occupé par la dernière ligne de données.
    axis.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncols=2)
    figure.tight_layout()
    return figure


def plot_domain_occupancy(frame: pd.DataFrame, size: tuple[float, float] = (7.2, 3.2)) -> Figure:
    """Place des valeurs observées dans le domaine déclaré, une barre par variable.

    Attend la sortie de `domain_check`. L'axe est relatif — 0 % la borne basse du
    domaine, 100 % la borne haute — ce qui met sur un même graphique une note sur
    20, un pourcentage et une échelle 1-5. Deux lectures d'un seul coup d'œil :
    un segment qui **sort du cadre** est une valeur impossible ; un segment qui
    n'occupe qu'une fraction du fond dit une borne déclarée trop large.
    """
    figure, axis = plt.subplots(figsize=size)
    positions = np.arange(len(frame))
    debut = frame["debut_%"].to_numpy(dtype="float64")
    fin = frame["fin_%"].to_numpy(dtype="float64")

    axis.barh(positions, 100.0, height=0.6, color=PALETTE["wash"], label="domaine déclaré")
    axis.barh(
        positions, fin - debut, left=debut, height=0.6, color=PALETTE["series_1"], label="observé"
    )
    for position, (start, stop, low, high) in enumerate(
        zip(debut, fin, frame["min"], frame["max"], strict=True)
    ):
        axis.text(start - 2, position, f"{low:g}", ha="right", va="center", fontsize=6.5)
        axis.text(stop + 2, position, f"{high:g}", ha="left", va="center", fontsize=6.5)

    axis.set_yticks(
        positions, [f"{c}  {d}" for c, d in zip(frame["colonne"], frame["domaine"], strict=True)]
    )
    axis.invert_yaxis()
    axis.set_xlim(-18, 118)
    axis.set_xlabel("position dans le domaine déclaré (%)")
    axis.grid(axis="y", visible=False)
    # Au-dessus du cadre, jamais dedans : sur des barres horizontales, un coin
    # « libre » est toujours occupé par la dernière ligne de données.
    axis.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncols=2)
    figure.tight_layout()
    return figure


def plot_heatmap(
    matrix: pd.DataFrame,
    axis: Axes | None = None,
    diverging: bool = True,
    annotate: bool = False,
    label: str = "",
) -> Figure:
    """Carte de chaleur d'une matrice carrée, avec son échelle.

    `diverging` choisit l'échelle selon la grandeur : signée (une corrélation, de
    -1 à 1, gris au centre) ou positive (un V de Cramér, de 0 à 1, une seule
    teinte). Se tromper d'échelle ferait lire un zéro comme un extrême.
    """
    if axis is None:
        side = 0.32 * len(matrix) + 2.2  # la figure grandit avec la matrice, pas les étiquettes
        figure, axis = plt.subplots(figsize=(side + 1.1, side))
    else:
        figure = axis.get_figure()

    limits = Normalize(-1, 1) if diverging else Normalize(0, 1)
    image = axis.imshow(
        matrix.to_numpy(dtype="float64"),
        cmap=DIVERGING if diverging else SEQUENTIAL,
        norm=limits,
    )
    axis.set_xticks(range(len(matrix)), matrix.columns.astype(str), rotation=90)
    axis.set_yticks(range(len(matrix)), matrix.index.astype(str))
    axis.grid(visible=False)
    figure.colorbar(image, ax=axis, shrink=0.72, label=label)

    if annotate:
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                cell = float(matrix.iat[row, column])
                axis.text(
                    column,
                    row,
                    f"{cell:.2f}".removeprefix("0"),
                    ha="center",
                    va="center",
                    fontsize=6.5,
                    # L'encre suit le fond : au-delà de la moitié de l'échelle, la
                    # cellule est trop sombre pour du texte foncé.
                    color=PALETTE["surface"] if abs(cell) > 0.55 else PALETTE["ink"],
                )
    figure.tight_layout()
    return figure


def show(figure: Figure) -> None:
    """Affiche une figure puis la referme — sans quoi le backend inline la rendrait deux fois."""
    from IPython.display import display

    display(figure)
    plt.close(figure)
