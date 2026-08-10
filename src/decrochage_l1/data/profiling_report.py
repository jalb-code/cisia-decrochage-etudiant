"""Rapport HTML de profilage — restitution complète de ce que `profiling` a mesuré.

Ce module ne mesure rien : il met en page. D'où une dépendance à **sens unique**
(`profiling` → `profiling_report`) et aucun import de `profiling` ici hors
typage — sans quoi les deux modules se citeraient en boucle.

Ce que le rapport ajoute à la vue d'écran (`CsvProfile.overview`) :

- les **quatorze indicateurs** au complet, dans une table **filtrable** (nom,
  type réel, type sémantique, colonnes constantes / non conformes / à manquants)
  et **triable** colonne par colonne ;
- l'**inventaire exhaustif des modalités** de chaque colonne qui en compte peu,
  ouvert en fenêtre modale depuis la cellule d'exemples : effectifs, part, et
  **écritures brutes** — la matière des décisions de recodage ;
- l'**inventaire des motifs d'écriture**, ouvert de la même façon depuis
  `n_motifs` : effectif, part et **exemple réel** de chaque forme rencontrée. Il
  corrige ce que le seul motif dominant laisse croire.

Le fichier produit est **autonome** : style et script embarqués, aucune ressource
distante, aucune dépendance JS. Il s'ouvre hors ligne, sans serveur. Les couleurs
suivent la palette de référence du projet (teintes catégorielles 1 à 3, rampe
séquentielle bleue), validée *all-pairs* dans les deux thèmes ; le type sémantique
porte toujours son **libellé**, la teinte n'étant qu'un repère secondaire.

Il contient des **valeurs brutes**, donc des données personnelles : sa destination
est hors dépôt (`settings.report_dir`, ignoré par `.gitignore`).
"""

# Annotations différées : `CsvProfile` n'est typé que pour la relecture, et n'est
# donc jamais importé à l'exécution (cf. la dépendance à sens unique ci-dessus).
from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from decrochage_l1.data.profiling import CsvProfile

# Rappel de fonctionnement, affiché en tête de rapport : le lecteur ne doit pas
# avoir à ouvrir le code pour savoir ce que mesure une colonne du tableau.
_NOTICE: tuple[tuple[str, str], ...] = (
    (
        "type_reel vs type_semantique",
        "Le premier est ce que pandas infère spontanément, le second ce que la colonne "
        "<em>représente</em>. Leur écart trahit une valeur textuelle intruse dans une colonne "
        "de nombres.",
    ),
    (
        "n_distinct vs n_distinct_normalise",
        "Le nombre de modalités avant et après uniformisation de l'écriture (casse, accents, "
        "espaces). Un écart signale des modalités qui n'en sont pas.",
    ),
    (
        "non_conforme_%",
        "La part des valeurs écrites hors de la forme canonique de leur type. "
        "<strong>Aucune n'est fausse</strong> : la mesure porte sur l'hétérogénéité d'écriture, "
        "celle qui empêche de compter ou d'agréger.",
    ),
    (
        "min / max",
        "Les bornes, lues sur la <strong>grandeur</strong> et non sur l'écriture : "
        "<code>9,5</code> ne dépasse pas <code>12.0 km</code>. Colonnes ordonnables seulement "
        "— nombres et dates.",
    ),
    (
        "motif d'écriture",
        "La forme généralisée des valeurs (<code>\\d{4}-\\d{2}-\\d{2}</code>). Renseigné pour "
        "les seules colonnes restées en texte alors qu'elles portent un nombre, une date ou un "
        "identifiant : ailleurs il ne dirait que l'ordre de grandeur ou la longueur d'un libellé.",
    ),
    (
        "n_motifs → motifs",
        "Le nombre de motifs est <strong>cliquable</strong> : il ouvre leur inventaire, avec "
        "effectif, part et <strong>exemple réel</strong>. À lire avant de conclure sur "
        "<code>couverture_motif_%</code> — une couverture de 33 % laisse croire à deux tiers de "
        "valeurs mal écrites, alors que les deux premiers motifs peuvent n'être que le même "
        "nombre à un chiffre près (<code>5.5</code> et <code>18.8</code>).",
    ),
    (
        "exemples → modalités",
        "Une cellule d'exemples <strong>cliquable</strong> ouvre l'inventaire exhaustif des "
        "modalités de la colonne : effectifs, part, et écritures brutes avec leurs espaces de "
        "bord rendus visibles.",
    ),
    (
        "Un tiret n'est pas un zéro",
        "<code>—</code> se lit « sans objet pour ce type de colonne », jamais « mesure nulle ». "
        "Un zéro, lui, est écrit <code>0</code>.",
    ),
)

# Familles de types sémantiques, pour un repère visuel de balayage. Trois teintes
# seulement (slots catégoriels 1 à 3) : au-delà, la palette ne tient plus les seuils
# de séparation *all-pairs*, et toutes les lignes cohabitent à l'écran.
_FAMILIES: dict[str, str] = {
    "entier": "nombre",
    "decimal": "nombre",
    "date": "temps",
    "texte": "texte",
    "categoriel": "texte",
}

# Colonnes de la table, dans l'ordre, avec la sorte de cellule à rendre.
_TABLE: tuple[tuple[str, str], ...] = (
    ("colonne", "name"),
    ("type_reel", "code"),
    ("type_semantique", "badge"),
    ("motif_dominant", "code"),
    ("couverture_motif_%", "num"),
    ("n_motifs", "patterns"),
    ("n_distinct", "num"),
    ("n_distinct_normalise", "num"),
    ("min", "code"),
    ("max", "code"),
    ("null_%", "meter"),
    ("non_conforme_%", "meter"),
    ("exemples", "examples"),
    ("remarques", "note"),
)

_DASH = '<span class="na" title="sans objet pour ce type de colonne">—</span>'

# Style embarqué : le rapport doit s'ouvrir hors ligne, donc aucune feuille distante.
# Deux points ne sont pas cosmétiques :
#   - `white-space: pre` sur les écritures brutes — sans lui le navigateur replierait
#     les espaces, effaçant justement le défaut à voir (« Gestion » face à «  Gestion  ») ;
#   - les jetons de thème sont déclarés trois fois (clair, `prefers-color-scheme`,
#     `[data-theme]`) pour que le choix explicite du lecteur l'emporte dans les deux sens.
_STYLE = """
:root {
  color-scheme: light;
  --plane: #f9f9f7; --surface: #fcfcfb; --raised: #ffffff;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --ring: rgba(11,11,11,.10); --wash: rgba(11,11,11,.04);
  --accent: #2a78d6; --track: #cde2fb; --fill: #2a78d6;
  --fam-nombre: #2a78d6; --fam-temps: #eb6834; --fam-texte: #1baf7a; --fam-autre: #898781;
  --shadow: 0 1px 2px rgba(11,11,11,.05), 0 10px 30px rgba(11,11,11,.07);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --plane: #0d0d0d; --surface: #1a1a19; --raised: #232321;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --ring: rgba(255,255,255,.10); --wash: rgba(255,255,255,.05);
    --accent: #3987e5; --track: #184f95; --fill: #3987e5;
    --fam-nombre: #3987e5; --fam-temps: #d95926; --fam-texte: #199e70; --fam-autre: #898781;
    --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px rgba(0,0,0,.45);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --plane: #0d0d0d; --surface: #1a1a19; --raised: #232321;
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --ring: rgba(255,255,255,.10); --wash: rgba(255,255,255,.05);
  --accent: #3987e5; --track: #184f95; --fill: #3987e5;
  --fam-nombre: #3987e5; --fam-temps: #d95926; --fam-texte: #199e70; --fam-autre: #898781;
  --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px rgba(0,0,0,.45);
}

* { box-sizing: border-box; }
body {
  margin: 0; padding: 1.5rem clamp(.75rem, 2.5vw, 2.25rem) 4rem;
  background: var(--plane); color: var(--ink);
  font: 400 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
h1 { font-size: 1.3rem; font-weight: 650; margin: 0; letter-spacing: -.01em; }
h2 { font-size: .95rem; font-weight: 650; margin: 0 0 .75rem; }
h3 { font-size: .8rem; font-weight: 650; margin: 0 0 .2rem; }
p { margin: 0; }
code { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: .93em; }
.sr-only {
  position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%);
}

/* --- En-tête ------------------------------------------------------------- */
.topbar {
  display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
  margin-bottom: 1.25rem;
}
.topbar .sub { color: var(--ink-2); font-size: .82rem; margin-top: .15rem; }
.topbar .sub b { font-weight: 600; color: var(--ink); font-variant-numeric: tabular-nums; }
.spacer { flex: 1 1 auto; }
button.ghost {
  font: inherit; font-size: .8rem; color: var(--ink-2); cursor: pointer;
  background: var(--surface); border: 1px solid var(--ring); border-radius: 8px;
  padding: .35rem .7rem; display: inline-flex; align-items: center; gap: .35rem;
}
button.ghost:hover { background: var(--wash); color: var(--ink); }
:where(button, input, select, summary):focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}

/* --- Cartes -------------------------------------------------------------- */
section {
  background: var(--surface); border: 1px solid var(--ring); border-radius: 14px;
  padding: 1rem 1.15rem; margin-bottom: 1rem;
}
.notice {
  border-left: 3px solid var(--accent);
  background: color-mix(in oklab, var(--accent) 4%, var(--surface));
}
.notice h2 { display: flex; align-items: center; gap: .45rem; color: var(--accent); }
.notice h2 svg { width: 15px; height: 15px; flex: none; }
.notice-grid {
  display: grid; gap: .7rem 1.5rem;
  grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
}
.notice-grid p { color: var(--ink-2); font-size: .8rem; line-height: 1.5; }
.notice-grid h3 { font-family: ui-monospace, Consolas, monospace; color: var(--ink); }

/* Trois colonnes : les sept propriétés tiennent en trois lignes au lieu de sept. */
.facts { display: grid; gap: .55rem; margin: 0; grid-template-columns: repeat(3, minmax(0, 1fr)); }
@media (max-width: 760px) { .facts { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.fact {
  background: var(--raised); border: 1px solid var(--ring); border-radius: 10px;
  padding: .5rem .7rem;
}
.fact dt {
  font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted);
}
.fact dd {
  margin: .15rem 0 0; font-size: .95rem; font-weight: 550;
  font-variant-numeric: tabular-nums; overflow-wrap: anywhere;
}

/* --- Barre de filtres ---------------------------------------------------- */
.toolbar {
  display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; margin-bottom: .75rem;
}
input[type="search"], select {
  font: inherit; font-size: .82rem; color: var(--ink);
  background: var(--raised); border: 1px solid var(--ring); border-radius: 8px;
  padding: .38rem .6rem;
}
input[type="search"] { min-width: 15rem; flex: 1 1 15rem; }
.chip {
  font: inherit; font-size: .78rem; color: var(--ink-2); cursor: pointer;
  background: var(--raised); border: 1px solid var(--ring); border-radius: 999px;
  padding: .3rem .7rem;
}
.chip:hover { background: var(--wash); }
.chip[aria-pressed="true"] {
  background: color-mix(in oklab, var(--accent) 14%, var(--surface));
  border-color: color-mix(in oklab, var(--accent) 45%, var(--surface));
  color: var(--ink);
}
.tally { font-size: .78rem; color: var(--muted); font-variant-numeric: tabular-nums; }

/* --- Table --------------------------------------------------------------- */
.table-wrap {
  max-height: 72vh; overflow: auto;
  border: 1px solid var(--ring); border-radius: 10px; background: var(--raised);
}
table.profil { border-collapse: separate; border-spacing: 0; font-size: .8rem; width: 100%; }
table.profil th, table.profil td {
  padding: .34rem .6rem; text-align: left; white-space: nowrap;
  border-bottom: 1px solid var(--grid);
}
table.profil thead th {
  position: sticky; top: 0; z-index: 2; cursor: pointer; user-select: none;
  background: var(--surface); color: var(--ink-2); font-weight: 600;
  font-family: ui-monospace, Consolas, monospace; font-size: .72rem;
}
table.profil thead th:hover { color: var(--ink); }
table.profil thead th::after { content: "↕"; opacity: .25; margin-left: .3rem; }
table.profil thead th[aria-sort="ascending"]::after { content: "↑"; opacity: 1; }
table.profil thead th[aria-sort="descending"]::after { content: "↓"; opacity: 1; }
table.profil tbody tr:hover td, table.profil tbody tr:hover th { background: var(--wash); }
table.profil th[scope="row"], table.profil thead th:first-child {
  position: sticky; left: 0; z-index: 1; background: var(--raised);
  font-weight: 600; box-shadow: 1px 0 0 var(--grid);
}
table.profil thead th:first-child { z-index: 3; background: var(--surface); }
table.profil tbody tr:hover th[scope="row"] {
  background: color-mix(in oklab, var(--wash), var(--raised));
}
.c-num, .c-meter { text-align: right; font-variant-numeric: tabular-nums; }
.c-code code { color: var(--ink-2); }
.na { color: var(--muted); }

.badge {
  display: inline-flex; align-items: center; gap: .35rem;
  border: 1px solid var(--ring); border-radius: 999px; padding: .1rem .5rem .1rem .4rem;
  font-size: .72rem; color: var(--ink-2); background: var(--surface);
}
.badge::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--fam-autre);
}
.badge.fam-nombre::before { background: var(--fam-nombre); }
.badge.fam-temps::before { background: var(--fam-temps); }
.badge.fam-texte::before { background: var(--fam-texte); }

.meter { display: inline-grid; justify-items: end; gap: 2px; min-width: 3.6rem; }
.track {
  width: 100%; height: 3px; border-radius: 2px; background: var(--track); overflow: hidden;
}
.track > i { display: block; height: 100%; background: var(--fill); }

.ex {
  font: inherit; font-size: .8rem; color: inherit; cursor: pointer; text-align: left;
  background: none; border: 0; border-radius: 6px; padding: .1rem .3rem;
  display: inline-flex; align-items: center; gap: .4rem; max-width: 100%;
}
.ex:hover { background: var(--wash); }
.ex:hover .count { border-color: color-mix(in oklab, var(--accent) 45%, var(--surface)); }
.clip {
  display: block; max-width: 24ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.c-note .clip { max-width: 26ch; color: var(--ink-2); }
.count {
  flex: none; font-size: .68rem; color: var(--ink-2); font-variant-numeric: tabular-nums;
  border: 1px solid var(--ring); border-radius: 999px; padding: 0 .35rem;
}
.empty { padding: 1.25rem; text-align: center; color: var(--muted); font-size: .85rem; }

/* --- Fenêtre modale ------------------------------------------------------ */
dialog {
  border: 0; padding: 0; border-radius: 14px; max-width: min(820px, 94vw);
  background: var(--surface); color: var(--ink); box-shadow: var(--shadow);
}
dialog::backdrop { background: rgba(11,11,11,.5); backdrop-filter: blur(2px); }
dialog header {
  display: flex; align-items: flex-start; gap: 1rem; padding: .9rem 1.1rem;
  border-bottom: 1px solid var(--grid); position: sticky; top: 0; background: var(--surface);
}
dialog h3 { font-size: 1rem; font-family: ui-monospace, Consolas, monospace; }
dialog .meta { font-size: .76rem; color: var(--muted); margin-top: .2rem; }
.modal-body { padding: .3rem 1.1rem 1.1rem; max-height: 68vh; overflow: auto; }
table.modalites { border-collapse: separate; border-spacing: 0; font-size: .8rem; width: 100%; }
table.modalites th {
  position: sticky; top: 0; background: var(--surface); text-align: left; color: var(--muted);
  font-size: .7rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
  padding: .45rem .5rem; border-bottom: 1px solid var(--grid);
}
table.modalites td {
  padding: .35rem .5rem; border-bottom: 1px solid var(--grid); vertical-align: middle;
}
table.modalites td:nth-child(2), table.modalites td:nth-child(3) {
  text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap;
}
table.modalites .mod { font-weight: 550; }
table.modalites .writings { display: flex; flex-wrap: wrap; gap: .25rem; }
code.raw {
  white-space: pre; background: var(--wash); border: 1px solid var(--ring);
  border-radius: 5px; padding: 0 .2rem; color: var(--ink-2);
}
"""

# Script embarqué : filtres, tri, modales et thème. Aucune dépendance externe —
# le rapport doit fonctionner depuis un simple `file://`, hors ligne.
_SCRIPT = """
(() => {
  const root = document.documentElement;
  const safe = { get: k => { try { return localStorage.getItem(k); } catch { return null; } },
                 set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* file:// */ } } };

  // --- Thème : préférence système par défaut, choix explicite mémorisé ---
  const toggle = document.getElementById('theme');
  let theme = safe.get('profil-theme')
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const paint = () => {
    root.dataset.theme = theme;
    toggle.textContent = theme === 'dark' ? '☀ Clair' : '☾ Sombre';
  };
  paint();
  toggle.addEventListener('click', () => {
    theme = theme === 'dark' ? 'light' : 'dark';
    safe.set('profil-theme', theme);
    paint();
  });

  // --- Filtres ---
  const table = document.getElementById('profil');
  const tbody = table.tBodies[0];
  const rows = [...tbody.rows];
  const term = document.getElementById('q');
  const real = document.getElementById('f-real');
  const sem = document.getElementById('f-sem');
  const chips = [...document.querySelectorAll('.chip')];
  const tally = document.getElementById('tally');
  const empty = document.getElementById('empty');

  const apply = () => {
    const needle = term.value.trim().toLowerCase();
    const flags = chips.filter(c => c.getAttribute('aria-pressed') === 'true')
                       .map(c => c.dataset.flag);
    let shown = 0;
    for (const tr of rows) {
      const own = tr.dataset.flags.split(' ');
      const ok = (!needle || tr.dataset.name.includes(needle))
        && (!real.value || tr.dataset.real === real.value)
        && (!sem.value || tr.dataset.semantic === sem.value)
        && flags.every(f => own.includes(f));
      tr.hidden = !ok;
      if (ok) shown++;
    }
    tally.textContent = shown + ' / ' + rows.length + ' colonnes';
    empty.hidden = shown > 0;
  };

  term.addEventListener('input', apply);
  real.addEventListener('change', apply);
  sem.addEventListener('change', apply);
  chips.forEach(c => c.addEventListener('click', () => {
    c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
    apply();
  }));
  document.getElementById('reset').addEventListener('click', () => {
    term.value = ''; real.value = ''; sem.value = '';
    chips.forEach(c => c.setAttribute('aria-pressed', 'false'));
    apply();
  });

  // --- Tri : numérique dès que les deux cellules portent une valeur, vides en fin ---
  table.querySelectorAll('thead th').forEach((th, index) => th.addEventListener('click', () => {
    const dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
    table.querySelectorAll('thead th').forEach(o => o.removeAttribute('aria-sort'));
    th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
    const key = tr => {
      const cell = tr.cells[index];
      return (cell.dataset.v !== undefined ? cell.dataset.v : cell.textContent).trim();
    };
    rows.sort((a, b) => {
      const x = key(a), y = key(b);
      if (!x || !y) return x ? -1 : y ? 1 : 0;
      const nx = Number(x), ny = Number(y);
      const numeric = x !== '' && y !== '' && !isNaN(nx) && !isNaN(ny);
      return (numeric ? nx - ny : x.localeCompare(y, 'fr')) * dir;
    });
    rows.forEach(tr => tbody.appendChild(tr));
  }));

  // --- Modales : le contenu vit dans un <template>, cloné à l'ouverture ---
  const dialog = document.getElementById('modal');
  const body = dialog.querySelector('.modal-body');
  document.querySelectorAll('.ex[data-modal]').forEach(button => {
    button.addEventListener('click', () => {
      dialog.querySelector('h3').textContent = button.dataset.title;
      dialog.querySelector('.meta').textContent = button.dataset.meta;
      body.replaceChildren(document.getElementById(button.dataset.modal).content.cloneNode(true));
      dialog.showModal();
    });
  });
  dialog.querySelector('.close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
})();
"""

_INFO_ICON = (
    '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">'
    '<path d="M8 0a8 8 0 100 16A8 8 0 008 0zm.9 12H7.1V6.6h1.8V12zM8 5.4A1.1 1.1 0 118 3.2a1.1 '
    '1.1 0 010 2.2z"/></svg>'
)


def _esc(value: object) -> str:
    """Échappe une valeur de la source : elle ne doit jamais devenir du balisage."""
    return html.escape(str(value))


def _num(value: object) -> str:
    """Valeur numérique d'une cellule pour le tri et les jauges ; vide si sans objet."""
    return "" if value == "" or value is None else str(value)


def _family(semantic_type: str) -> str:
    """Famille de types sémantiques, pour la teinte de repère du badge."""
    return _FAMILIES.get(semantic_type, "autre")


def _filename(source: Path) -> str:
    """Nom du rapport, dérivé de celui de la source (espaces compris — cf. `dataset ....csv`)."""
    return f"profil-{source.stem.replace(' ', '_')}.html"


def _notice() -> str:
    """Rappel de fonctionnement : ce que mesure chaque indicateur, pleine largeur."""
    items = "".join(f"<div><h3>{title}</h3><p>{text}</p></div>" for title, text in _NOTICE)
    return (
        '<section class="notice" aria-labelledby="notice-title">'
        f'<h2 id="notice-title">{_INFO_ICON} Comment lire ce rapport</h2>'
        f'<div class="notice-grid">{items}</div></section>'
    )


def _facts(frame: pd.DataFrame) -> str:
    """Propriétés du fichier en tuiles — trois colonnes plutôt qu'une liste en hauteur."""
    tiles = "".join(
        f'<div class="fact"><dt>{_esc(prop)}</dt><dd>{_esc(value)}</dd></div>'
        for prop, value in zip(frame["Propriété"], frame["Valeur"], strict=True)
    )
    return f'<section><h2>Fichier</h2><dl class="facts">{tiles}</dl></section>'


def _options(values: pd.Series, label: str, select_id: str) -> str:
    """Liste déroulante peuplée par les valeurs **présentes** dans le fichier."""
    options = "".join(f"<option>{_esc(v)}</option>" for v in sorted(values.unique()))
    return (
        f'<label class="sr-only" for="{select_id}">{label}</label>'
        f'<select id="{select_id}"><option value="">{label}</option>{options}</select>'
    )


def _meter(value: object) -> str:
    """Pourcentage : le chiffre, doublé d'une jauge à échelle absolue (0 à 100 %).

    Échelle absolue et non relative au maximum observé : une colonne à 4 % doit
    *paraître* à 4 %, sans quoi la jauge flatterait le désordre.
    """
    number = float(value)
    if number == 0:
        return '<td class="c-meter" data-v="0"><span class="na">0</span></td>'
    return (
        f'<td class="c-meter" data-v="{number}"><span class="meter">{number}'
        f'<span class="track"><i style="width:{min(number, 100)}%"></i></span></span></td>'
    )


def _examples(record: dict, breakdown: pd.DataFrame | None, modal_id: str) -> str:
    """Cellule d'exemples : quelques valeurs, cliquables si les modalités s'énumèrent."""
    examples = _esc(record["exemples"])
    if breakdown is None or breakdown.empty:
        return f'<td class="c-ex"><span class="clip" title="{examples}">{examples}</span></td>'

    writings = sum(len(w) for w in breakdown["ecritures"])
    meta = (
        f"{len(breakdown)} modalités · {int(breakdown['n'].sum())} valeurs renseignées "
        f"· {writings} écritures distinctes"
    )
    return (
        f'<td class="c-ex"><button class="ex" data-modal="{modal_id}"'
        f' data-title="{_esc(record["colonne"])}" data-meta="{_esc(meta)}"'
        f' title="Voir les {len(breakdown)} modalités">'
        f'<span class="clip">{examples}</span>'
        f'<span class="count">{len(breakdown)}</span></button></td>'
    )


def _patterns(record: dict, breakdown: pd.DataFrame | None, modal_id: str) -> str:
    """Cellule du nombre de motifs, cliquable quand ils s'énumèrent.

    Muette lorsque `n_motifs` est vide : le profil juge alors le motif non
    informatif (texte libre, colonne déjà typée), et l'inventaire le serait tout
    autant.
    """
    text = _esc(record["n_motifs"])
    plain = f'<td class="c-num" data-v="{_num(record["n_motifs"])}">{text or _DASH}</td>'
    if not text or breakdown is None or breakdown.empty:
        return plain

    meta = f"{len(breakdown)} motifs · {int(breakdown['n'].sum())} valeurs renseignées"
    return (
        f'<td class="c-num" data-v="{_num(record["n_motifs"])}">'
        f'<button class="ex" data-modal="{modal_id}" data-title="{_esc(record["colonne"])}"'
        f' data-meta="{_esc(meta)}" title="Voir les {len(breakdown)} motifs d\'écriture">'
        f'<span class="count">{text}</span></button></td>'
    )


def _cell(
    kind: str,
    value: object,
    record: dict,
    breakdown: pd.DataFrame | None,
    modal_id: str,
    patterns: pd.DataFrame | None = None,
    pattern_id: str = "",
) -> str:
    """Rend une cellule selon sa sorte ; une valeur sans objet devient un tiret."""
    text = _esc(value)
    match kind:
        case "name":
            return f'<th scope="row">{text}</th>'
        case "code":
            return f'<td class="c-code">{f"<code>{text}</code>" if text else _DASH}</td>'
        case "num":
            return f'<td class="c-num" data-v="{_num(value)}">{text or _DASH}</td>'
        case "badge":
            return f'<td><span class="badge fam-{_family(str(value))}">{text}</span></td>'
        case "meter":
            return _meter(value)
        case "examples":
            return _examples(record, breakdown, modal_id)
        case "patterns":
            return _patterns(record, patterns, pattern_id)
        case _:
            return f'<td class="c-note"><span class="clip" title="{text}">{text}</span></td>'


def _row(
    record: dict,
    breakdown: pd.DataFrame | None,
    modal_id: str,
    patterns: pd.DataFrame | None = None,
    pattern_id: str = "",
) -> str:
    """Une ligne de la table, porteuse des attributs sur lesquels filtrent les contrôles."""
    flags = [
        flag
        for flag, holds in (
            ("constante", record["n_distinct"] == 1),
            ("nonconforme", float(record["non_conforme_%"]) > 0),
            ("manquants", float(record["null_%"]) > 0),
        )
        if holds
    ]
    cells = "".join(
        _cell(kind, record[key], record, breakdown, modal_id, patterns, pattern_id)
        for key, kind in _TABLE
    )
    return (
        f'<tr data-name="{_esc(str(record["colonne"]).lower())}"'
        f' data-real="{_esc(record["type_reel"])}"'
        f' data-semantic="{_esc(record["type_semantique"])}"'
        f' data-flags="{" ".join(flags)}">{cells}</tr>'
    )


def _meter_cell(part: object) -> str:
    """Cellule de part, avec sa jauge — commune aux deux inventaires."""
    return (
        f'<td><span class="meter">{part}'
        f'<span class="track"><i style="width:{min(float(part), 100)}%"></i></span></span></td>'
    )


def _modal_template(record: dict, breakdown: pd.DataFrame, modal_id: str) -> str:
    """Inventaire des modalités d'une colonne, en réserve dans un `<template>`."""
    rows = "".join(
        "<tr>"
        f'<td class="mod">{_esc(modality)}</td><td>{int(n)}</td>'
        + _meter_cell(part)
        + '<td><span class="writings">'
        + "".join(f'<code class="raw">«{_esc(w)}»</code>' for w in writings)
        + "</span></td></tr>"
        for modality, n, part, writings in breakdown.itertuples(index=False)
    )
    return (
        f'<template id="{modal_id}"><table class="modalites"><thead><tr>'
        "<th>modalité</th><th>n</th><th>part %</th><th>écritures rencontrées</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></template>"
    )


def _pattern_template(breakdown: pd.DataFrame, modal_id: str) -> str:
    """Inventaire des motifs d'écriture d'une colonne, en réserve dans un `<template>`.

    L'**exemple** est ce qui rend le motif lisible : `\\d{2}\\.\\d` ne parle à
    personne, `18.8` se comprend d'un coup d'œil.
    """
    rows = "".join(
        "<tr>"
        f'<td><code class="raw">{_esc(pattern)}</code></td><td>{int(n)}</td>'
        + _meter_cell(part)
        + f'<td><code class="raw">«{_esc(example)}»</code></td></tr>'
        for pattern, n, part, example in breakdown.itertuples(index=False)
    )
    return (
        f'<template id="{modal_id}"><table class="modalites"><thead><tr>'
        "<th>motif</th><th>n</th><th>part %</th><th>exemple</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></template>"
    )


def _columns_section(
    columns: pd.DataFrame,
    breakdowns: dict[str, pd.DataFrame | None],
    patterns: dict[str, pd.DataFrame | None] | None = None,
) -> str:
    """Table des quatorze indicateurs : filtres, tri, modalités et motifs dépliables."""
    patterns = patterns or {}
    headers = "".join(f"<th>{_esc(key)}</th>" for key, _ in _TABLE)
    records = columns.to_dict(orient="records")
    ids = {str(record["colonne"]): f"m{index}" for index, record in enumerate(records)}
    pattern_ids = {str(record["colonne"]): f"p{index}" for index, record in enumerate(records)}

    rows, templates = [], []
    for record in records:
        name = str(record["colonne"])
        breakdown, pattern = breakdowns.get(name), patterns.get(name)
        rows.append(_row(record, breakdown, ids[name], pattern, pattern_ids[name]))
        if breakdown is not None and not breakdown.empty:
            templates.append(_modal_template(record, breakdown, ids[name]))
        if record["n_motifs"] != "" and pattern is not None and not pattern.empty:
            templates.append(_pattern_template(pattern, pattern_ids[name]))

    chips = "".join(
        f'<button class="chip" data-flag="{flag}" aria-pressed="false" title="{title}">{label}'
        "</button>"
        for flag, label, title in (
            ("constante", "n_distinct = 1", "Colonnes constantes : aucune information"),
            ("nonconforme", "non conformes", "Colonnes dont l'écriture est hétérogène"),
            ("manquants", "manquants", "Colonnes comportant des valeurs absentes"),
        )
    )
    return (
        f"<section><h2>Colonnes</h2>"
        '<div class="toolbar">'
        '<label class="sr-only" for="q">Filtrer par nom de colonne</label>'
        '<input type="search" id="q" placeholder="Filtrer par nom de colonne…">'
        f"{_options(columns['type_reel'], 'Tout type réel', 'f-real')}"
        f"{_options(columns['type_semantique'], 'Tout type sémantique', 'f-sem')}"
        f"{chips}"
        f'<span class="tally" id="tally" aria-live="polite">{len(records)} / {len(records)}'
        " colonnes</span>"
        '<button class="ghost" id="reset">Réinitialiser</button>'
        "</div>"
        '<div class="table-wrap"><table class="profil" id="profil">'
        f"<thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        '<p class="empty" id="empty" hidden>Aucune colonne ne correspond à ces filtres.</p>'
        f"</div></section>{''.join(templates)}"
    )


def to_html(
    profile: CsvProfile,
    breakdowns: dict[str, pd.DataFrame | None],
    patterns: dict[str, pd.DataFrame | None] | None = None,
) -> str:
    """Rapport complet d'un profil, en une page HTML autonome.

    Aucun horodatage : le contenu ne dépend que des données, donc deux exécutions
    sur la même source rendent le même fichier — la date de modification suffit à
    situer le rapport.
    """
    file = profile.file
    title = _esc(file.path.name)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Profilage — {title}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="topbar">
  <div>
    <h1>Profilage — {title}</h1>
    <p class="sub"><b>{file.n_rows}</b> lignes · <b>{file.n_columns}</b> colonnes ·
      <b>{file.n_duplicate_rows}</b> lignes en double · {_esc(file.encoding)}</p>
  </div>
  <span class="spacer"></span>
  <button class="ghost" id="theme" type="button">☾ Sombre</button>
</div>
{_notice()}
{_facts(file.to_frame())}
{_columns_section(profile.columns, breakdowns, patterns)}
<dialog id="modal" aria-labelledby="modal-title">
  <header class="modal-head">
    <div><h3 id="modal-title"></h3><p class="meta"></p></div>
    <span class="spacer"></span>
    <button class="ghost close" type="button" aria-label="Fermer">✕</button>
  </header>
  <div class="modal-body"></div>
</dialog>
<script>{_SCRIPT}</script>
</body>
</html>
"""


def write(
    profile: CsvProfile,
    breakdowns: dict[str, pd.DataFrame | None],
    patterns: dict[str, pd.DataFrame | None] | None,
    directory: Path,
) -> Path:
    """Écrit le rapport dans `directory` (créé au besoin) ; retourne le chemin produit."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _filename(profile.file.path)
    path.write_text(to_html(profile, breakdowns, patterns), encoding="utf-8")
    return path
