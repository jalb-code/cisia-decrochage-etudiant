/* Maquette de présentation — vanilla JS, zéro dépendance de framework (Lucide en CDN).
   Aucune règle métier ici : la page relaie au service, qui valide, convertit, borne et score.
   La clé d'API vit dans le navigateur (localStorage) : posture démo assumée, usage localhost. */

const State = {
  apiBase: localStorage.getItem("dl1.apiBase") || "http://localhost:8000",
  apiKey: localStorage.getItem("dl1.apiKey") || "",
  grafana: localStorage.getItem("dl1.grafana") || "http://localhost:3000",
  prometheus: localStorage.getItem("dl1.prometheus") || "http://localhost:9090",
  theme: localStorage.getItem("dl1.theme") || "light",
  fiche: null,
  seuil: null,
};

/* Formulaire Dossier : STATIQUE (construit ici, pas depuis le service). À synchroniser avec
   les colonnes d'entrée du contrat du modèle final (§9). Une valeur vide n'est pas envoyée.
   Bornes affichées = celles que le service refuse ; une borne haute ouverte s'écrit « ≥ 0 ». */
const CHAMPS = [
  { col: "age", label: "Âge", bornes: "≥ 0", theme: "Parcours" },
  { col: "nb_ue_total", label: "UE suivies", bornes: "≥ 0", theme: "Parcours" },
  { col: "taux_presence_pct", label: "Taux de présence", bornes: "[0 ; 100] %", theme: "Assiduité" },
  { col: "nb_devoirs_total", label: "Devoirs attendus", bornes: "≥ 0", theme: "Assiduité" },
  { col: "nb_devoirs_rendus", label: "Devoirs rendus", bornes: "≥ 0", theme: "Assiduité" },
  { col: "retards_rendus", label: "Rendus en retard", bornes: "≥ 0", theme: "Assiduité" },
  { col: "heures_lms_total", label: "Heures sur le LMS", bornes: "≥ 0", theme: "Engagement" },
  { col: "messages_forum", label: "Messages forum", bornes: "≥ 0", theme: "Engagement" },
  { col: "motivation", label: "Motivation", bornes: "[1 ; 5]", theme: "Ressenti" },
  { col: "satisfaction", label: "Satisfaction", bornes: "[1 ; 5]", theme: "Ressenti" },
  { col: "sentiment_appartenance", label: "Sentiment d'appartenance", bornes: "[1 ; 5]", theme: "Ressenti" },
];

/* Champs catégoriels du contrat. Le schéma attend les modalités CANONIQUES (minuscule, sans
   accent) : chaque option porte `[valeur_canonique, libellé_affiché]`. `mention_bac` est
   ordinale, `filiere` et `bac_type` nominales. */
const CATEGORIELLES = [
  { col: "mention_bac", label: "Mention au bac", theme: "Parcours",
    options: [["passable", "Passable"], ["assez bien", "Assez bien"], ["bien", "Bien"], ["tres bien", "Très bien"]] },
  { col: "bac_type", label: "Type de bac", theme: "Parcours",
    options: [["general", "Général"], ["technologique", "Technologique"], ["professionnel", "Professionnel"]] },
  { col: "filiere", label: "Filière", theme: "Parcours",
    options: [["biologie", "Biologie"], ["droit", "Droit"], ["gestion", "Gestion"], ["informatique", "Informatique"], ["lettres", "Lettres"], ["mathematiques", "Mathématiques"], ["psychologie", "Psychologie"], ["staps", "STAPS"]] },
];

/* Colonnes par nature, pour normaliser une saisie avant envoi (le contrat d'entrée est typé). */
const NUM_COLS = CHAMPS.map((c) => c.col);
const CAT_COLS = CATEGORIELLES.map((c) => c.col);

/* Colonnes attendues d'un fichier de campagne = colonnes d'entrée du contrat. À synchroniser
   avec les input_columns. `reference_dossier` est facultative. */
const EXPECTED_COLUMNS = [...CHAMPS.map((c) => c.col), ...CATEGORIELLES.map((c) => c.col)];

/* Dossier d'exemple, source unique du bouton « Remplir un exemple » et du modèle CSV.
   Écriture volontairement « réaliste » (« 72 % », accents) : le service la conforme. Cohérence
   respectée : nb_devoirs_rendus ≤ nb_devoirs_total, retards_rendus ≤ nb_devoirs_rendus. */
const DOSSIER_EXEMPLE = {
  age: "19",
  nb_ue_total: "6",
  taux_presence_pct: "72",
  nb_devoirs_total: "10",
  nb_devoirs_rendus: "6",
  retards_rendus: "3",
  heures_lms_total: "18",
  messages_forum: "1",
  motivation: "2",
  satisfaction: "3",
  sentiment_appartenance: "2",
  mention_bac: "assez bien",
  bac_type: "general",
  filiere: "informatique",
};

const $ = (sel) => document.querySelector(sel);
const el = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};
const refreshIcons = () => window.lucide && window.lucide.createIcons();
const fmtPct = (x) => (x == null ? "—" : (x * 100).toFixed(1) + " %");
const fmtNum = (x, d = 2) => (x == null ? "—" : Number(x).toFixed(d));

/* Normalisation avant envoi — le client est la couche d'intégration : il adapte la saisie au
   contrat typé du service (nombres propres, modalités canoniques). Le service, lui, reste
   strict et refuse ce qui ne s'y conforme pas. */
const toNumber = (v) => {
  const s = String(v).replace("%", "").replace(",", ".").trim();
  if (s === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : v; // non convertible : renvoyé tel quel, le service refusera
};
const canon = (v) =>
  String(v).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim().replace(/\s+/g, " ");

/* Un dossier prêt à envoyer : numériques convertis, catégorielles canoniques, vides omis
   (une absence est imputée par le modèle). Les colonnes inconnues passent — le service les refuse. */
function cleanRow(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v === "" || v == null) continue;
    if (NUM_COLS.includes(k)) out[k] = toNumber(v);
    else if (CAT_COLS.includes(k)) out[k] = canon(v);
    else out[k] = v;
  }
  return out;
}

let toastTimer;
function toast(message, type = "") {
  const t = $("#toast");
  t.className = "toast" + (type ? " " + type : "");
  const icon = type === "danger" ? "alert-triangle" : type === "success" ? "check-circle" : "info";
  t.innerHTML = `<i data-lucide="${icon}"></i><span></span>`;
  t.querySelector("span").textContent = message;
  t.hidden = false;
  refreshIcons();
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3600);
}

async function api(path, { method = "GET", body = null, key = true } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (key && State.apiKey) headers["X-API-Key"] = State.apiKey;
  const res = await fetch(State.apiBase + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });
  const raw = await res.text();
  let data = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = raw;
  }
  if (!res.ok) throw { status: res.status, data };
  return data;
}

/* --- Thème clair / sombre --- */
function applyTheme(theme) {
  State.theme = theme;
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("dl1.theme", theme);
  const btn = $("#btn-theme");
  if (btn) btn.innerHTML = `<i data-lucide="${theme === "dark" ? "sun" : "moon"}"></i>`;
  refreshIcons();
}

/* --- Bandeau d'état : service joignable et prêt, rafraîchi périodiquement --- */
async function refreshStatus() {
  const pill = $("#service-pill");
  const label = $("#service-label");
  pill.className = "pill";
  try {
    const ready = await api("/ready", { key: false });
    if (ready.ready) {
      pill.classList.add("ok");
      label.textContent = "API prête";
      State.seuil = ready.seuil;
    } else {
      pill.classList.add("ko");
      label.textContent = "modèle indisponible";
    }
  } catch {
    pill.classList.add("ko");
    label.textContent = "API injoignable";
    State.seuil = null;
  }
  $("#seuil-label").textContent = State.seuil == null ? "seuil —" : `seuil ${fmtNum(State.seuil, 3)}`;
}

async function loadFiche() {
  try {
    State.fiche = await api("/v1/modele");
  } catch {
    State.fiche = null;
  }
}

/* --- Explicabilité : barres divergentes protège / aggrave --- */
function contribBars(items, labelOf = (k) => k) {
  const rows = items.filter((it) => Math.abs(it.contribution) > 1e-9);
  const maxAbs = Math.max(1e-9, ...rows.map((it) => Math.abs(it.contribution)));
  return rows
    .map((it) => {
      const w = (Math.abs(it.contribution) / maxAbs) * 50;
      const side = it.contribution > 0 ? "aggrave" : "protege";
      return `<div class="contrib">
        <span>${labelOf(it.key)}</span>
        <span class="bar"><span class="fill ${side}" style="width:${w.toFixed(1)}%"></span></span>
        <span class="val">${it.contribution > 0 ? "+" : ""}${it.contribution.toFixed(2)}</span>
      </div>`;
    })
    .join("");
}
const themeItems = (list) => (list || []).map((t) => ({ key: t.theme, contribution: t.contribution }));
const variableItems = (list) => (list || []).map((v) => ({ key: v.variable, contribution: v.contribution }));

/* Libellés humains des variables, pour l'explicabilité par variable (colonne -> label lisible). */
const LABELS = {
  ...Object.fromEntries([...CHAMPS, ...CATEGORIELLES].map((c) => [c.col, c.label])),
  taux_rendu: "Taux de rendu",
  ratio_retards: "Ratio de retards",
};
const labelVariable = (col) => LABELS[col] || col;

/* --- Écran : une campagne --- */
function screenCampagne() {
  const content = $("#content");
  content.appendChild(
    el(`<div class="page-head"><h2>Scorer une campagne</h2>
      <p>Un fichier tabulaire, une ligne par étudiant. Chaque ligne est envoyée au service, qui la valide et la score — ou la refuse en nommant le champ en cause.</p></div>`)
  );
  const card = el(`<div class="card">
    <div class="row-actions" style="margin:0;align-items:center;flex-wrap:wrap">
      <span class="file-picker">
        <input type="file" id="csv" accept=".csv,.tsv,.txt" hidden />
        <button class="btn btn-ghost" id="btn-choose"><i data-lucide="file-up"></i> Choisir un fichier</button>
        <span id="file-name" class="muted">Aucun fichier</span>
      </span>
      <label class="muted"><input type="checkbox" id="derive" checked /> mesurer la dérive</label>
      <button class="btn btn-ghost" id="btn-format"><i data-lucide="help-circle"></i> Aide sur le format</button>
      <button class="btn btn-ghost" id="btn-modele-csv"><i data-lucide="download"></i> Télécharger un modèle</button>
      <button class="btn btn-primary" id="btn-scorer"><i data-lucide="play"></i> Scorer la campagne</button>
    </div>
    <div id="format-help" hidden></div>
    <div class="hint" id="csv-info"></div>
  </div>`);
  content.appendChild(card);
  content.appendChild(el(`<div id="campagne-result"></div>`));
  refreshIcons();

  $("#btn-format").onclick = () => {
    const help = $("#format-help");
    help.hidden = !help.hidden;
    help.innerHTML = help.hidden
      ? ""
      : `<div class="alert" style="background:var(--surface-2);border:1px solid var(--border);margin-top:12px">
        <strong>Format attendu</strong> — fichier tabulaire (CSV/TSV), UTF-8, une ligne d'en-tête puis une ligne par étudiant.
        <ul style="margin:8px 0 0;padding-left:18px;line-height:1.7">
          <li>séparateur <code>,</code> ou <code>;</code> (détecté automatiquement) ;</li>
          <li>une cellule vide = valeur manquante (imputée par le service) ;</li>
          <li>écriture « sale » acceptée (<code>52,4 %</code>, <code>INFORMATIQUE</code>) : normalisée avant envoi (nombres, modalités canoniques) ;</li>
          <li><code>reference_dossier</code> facultative (générée si absente) ; toute colonne hors périmètre est refusée en la nommant.</li>
        </ul>
        <div style="margin-top:8px">Colonnes attendues : <code>reference_dossier</code>, <code>${EXPECTED_COLUMNS.join("</code>, <code>")}</code>.</div>
      </div>`;
    refreshIcons();
  };

  $("#btn-modele-csv").onclick = () => downloadTemplate();
  $("#btn-choose").onclick = () => $("#csv").click();

  let rows = [];
  $("#csv").onchange = async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    $("#file-name").textContent = file.name;
    rows = parseTable(await file.text());
    $("#csv-info").innerHTML = precheck(rows);
  };

  $("#btn-scorer").onclick = async () => {
    if (!rows.length) return toast("Choisir d'abord un fichier.");
    try {
      const derive = $("#derive").checked ? "?derive=true" : "";
      const res = await api(`/v1/predict-cohorte${derive}`, { method: "POST", body: { dossiers: rows.map(cleanRow) } });
      renderCampagne($("#campagne-result"), res);
    } catch (e) {
      showError(e);
    }
  };
}

/* Contrôle avant envoi — l'appelant corrige avant de solliciter le service. Le service reste
   l'autorité : ce contrôle guide, il ne remplace pas sa validation. */
function precheck(rows) {
  if (!rows.length) return "Aucune ligne lue.";
  const header = Object.keys(rows[0]);
  const allowed = new Set(["reference_dossier", ...EXPECTED_COLUMNS]);
  const inconnues = header.filter((h) => !allowed.has(h));
  const absentes = EXPECTED_COLUMNS.filter((c) => !header.includes(c));
  let msg = `${rows.length} lignes lues, ${header.length} colonnes.`;
  if (inconnues.length) msg += ` <span style="color:var(--warning)">Colonnes non reconnues (seront refusées par le service) : ${inconnues.join(", ")}.</span>`;
  if (absentes.length) msg += ` Colonnes attendues absentes (traitées comme manquantes) : ${absentes.join(", ")}.`;
  return msg;
}

function downloadTemplate() {
  const cols = ["reference_dossier", ...EXPECTED_COLUMNS];
  const exemple = cols.map((c) => (c === "reference_dossier" ? "etu-001" : DOSSIER_EXEMPLE[c] ?? ""));
  const csv = cols.join(",") + "\n" + exemple.join(",") + "\n";
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "modele-campagne.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

function parseTable(text) {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim() !== "");
  if (!lines.length) return [];
  // Séparateur détecté par comptage sur l'en-tête — même règle que la chaîne de préparation.
  const sep = (lines[0].match(/;/g) || []).length > (lines[0].match(/,/g) || []).length ? ";" : ",";
  const header = lines[0].split(sep).map((h) => h.trim());
  return lines.slice(1).map((line, i) => {
    const cells = line.split(sep);
    const obj = {};
    header.forEach((h, j) => (obj[h] = (cells[j] ?? "").trim()));
    if (!obj.reference_dossier) obj.reference_dossier = `ligne-${i + 1}`;
    return obj;
  });
}

/* État de la vue campagne : les résultats bruts et les réglages de tri/filtre/pagination.
   Reconstruit à chaque scoring ; le tableau se re-rend depuis lui, sans re-solliciter le service. */
let CAMPAGNE = null;
const PAGE_SIZES = [25, 50, 100];

const sigBadge = (r, full = false) =>
  r.__refused
    ? `<span class="badge badge-soft">refusé</span>`
    : r.signaled == null
      ? "—"
      : r.signaled
        ? `<span class="badge badge-signale">signalé</span>`
        : `<span class="badge badge-non">${full ? "non signalé" : "non"}</span>`;

/* Valeur de tri d'une colonne ; les manquants numériques passent en fin (−∞ / chaîne vide). */
function sortValue(r, key) {
  if (key === "reference") return (r.reference ?? "").toLowerCase();
  if (key === "signaled") return r.signaled == null ? -1 : r.signaled ? 1 : 0;
  const v = r[key];
  return v == null ? -Infinity : v;
}

/* Vue courante : filtre (référence + signalés) puis tri. La pagination tranche ensuite. */
function campagneView() {
  const st = CAMPAGNE;
  let rows = st.rows;
  const q = st.filter.trim().toLowerCase();
  if (q) rows = rows.filter((r) => (r.reference ?? "").toLowerCase().includes(q));
  if (st.signaledOnly) rows = rows.filter((r) => r.signaled === true);
  if (st.sortKey) {
    const dir = st.sortDir === "asc" ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      const va = sortValue(a, st.sortKey);
      const vb = sortValue(b, st.sortKey);
      return va < vb ? -dir : va > vb ? dir : 0;
    });
  }
  return rows;
}

/* Re-rend le corps du tableau, les flèches de tri et l'état de la pagination. */
function refreshCampagneTable() {
  const st = CAMPAGNE;
  const view = campagneView();
  const pages = Math.max(1, Math.ceil(view.length / st.pageSize));
  st.page = Math.min(Math.max(1, st.page), pages);
  const start = (st.page - 1) * st.pageSize;
  const pageRows = view.slice(start, start + st.pageSize);

  const tbody = $("#camp-tbody");
  tbody.innerHTML =
    pageRows
      .map(
        (r) =>
          `<tr class="clickable${r.__refused ? " refused" : ""}" data-i="${r.__i}"><td>${r.reference}</td><td>${fmtPct(r.probability)}</td>
        <td>${fmtNum(r.moyenne_finale, 1)}</td><td>${sigBadge(r)}</td></tr>`
      )
      .join("") || `<tr><td colspan="4" class="muted">Aucun dossier ne correspond au filtre.</td></tr>`;

  document.querySelectorAll("#camp-thead th.sortable").forEach((th) => {
    const active = th.dataset.key === st.sortKey;
    th.classList.toggle("active", active);
    th.querySelector(".arrow").textContent = active ? (st.sortDir === "asc" ? "▲" : "▼") : "↕";
  });

  const total = view.length;
  $("#camp-count").textContent =
    total === st.rows.length
      ? `${total} dossier${total > 1 ? "s" : ""}`
      : `${total} sur ${st.rows.length}`;
  $("#camp-page").textContent = `page ${st.page} / ${pages}`;
  $("#camp-prev").disabled = st.page <= 1;
  $("#camp-next").disabled = st.page >= pages;
}

/* Export CSV de la vue courante (filtre + tri appliqués) — le livrable opérationnel de la campagne.
   Séparateur « ; », BOM UTF-8 pour Excel, virgule décimale française. */
function exportCampagne() {
  const header = ["reference_dossier", "probabilite_abandon", "note_finale_estimee", "signale", "motif_refus"];
  const lines = [header.join(";")];
  campagneView().forEach((r) => {
    const proba = r.probability == null ? "" : r.probability.toFixed(4).replace(".", ",");
    const note = r.moyenne_finale == null ? "" : r.moyenne_finale.toFixed(1).replace(".", ",");
    const sig = r.__refused ? "refusé" : r.signaled == null ? "" : r.signaled ? "oui" : "non";
    const motif = r.__refused ? r.errors.map((e) => `${e.champ}: ${e.message}`).join(" · ") : "";
    lines.push([r.reference, proba, note, sig, motif].join(";"));
  });
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "campagne-scoree.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

/* Tiroir latéral : créé une fois, réutilisé. Fermé au clic sur l'arrière-plan ou sur Échap. */
function ensureDrawer() {
  if ($("#drawer")) return;
  const overlay = el(`<div class="drawer-overlay" id="drawer-overlay"></div>`);
  const drawer = el(`<aside class="drawer" id="drawer" role="dialog" aria-modal="true"></aside>`);
  document.body.appendChild(overlay);
  document.body.appendChild(drawer);
  overlay.onclick = closeDrawer;
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeDrawer());
}
function closeDrawer() {
  $("#drawer")?.classList.remove("open");
  $("#drawer-overlay")?.classList.remove("open");
}

/* Ouvre le tiroir sur un dossier scoré : proba, note, indicateur, et l'explicabilité complète
   (par thème puis par variable). `ctx` porte le seuil appliqué et l'avertissement — de la campagne
   (`CAMPAGNE`) ou de la réponse d'un dossier unique — pour que le tiroir serve les deux écrans. */
function openDossierPanel(r, ctx) {
  ensureDrawer();
  if (r.__refused) {
    openRefusePanel(r);
    return;
  }
  $("#drawer").innerHTML = `
    <div class="drawer-head">
      <h3>${r.reference}</h3>
      <button class="close" id="drawer-close" aria-label="Fermer"><i data-lucide="x"></i></button>
    </div>
    <div class="stat-row" style="gap:28px;margin-top:6px">
      <div><div class="hint">probabilité d'abandon</div><div class="big-proba" style="font-size:32px">${fmtPct(r.probability)}</div></div>
      <div><div class="hint">note /20</div><div class="big-proba" style="font-size:26px">${fmtNum(r.moyenne_finale, 1)}</div></div>
    </div>
    <div style="margin:12px 0">${sigBadge(r, true)} <span class="hint" style="display:inline-block;margin-left:6px">seuil ${fmtNum(ctx.seuil, 3)} (${ctx.provenance})</span></div>
    <h3 style="margin-top:16px">Ce qui pèse sur l'estimation — par thème</h3>
    ${contribBars(themeItems(r.contributions_theme))}
    <h3 style="margin-top:16px">Détail — par variable</h3>
    ${contribBars(variableItems(r.contributions_variable), labelVariable)}
    <div class="note-art22">${ctx.avertissement}</div>`;
  $("#drawer-close").onclick = closeDrawer;
  $("#drawer").classList.add("open");
  $("#drawer-overlay").classList.add("open");
  refreshIcons();
}

/* Ouvre le tiroir sur un dossier refusé : le champ en cause et son motif, un par ligne.
   Pas de score — le service ne score pas une ligne invalide (refus explicite, jamais muet). */
function openRefusePanel(r) {
  const motifs = r.errors
    .map((e) => `<tr><td><code>${e.champ}</code></td><td>${e.message}</td></tr>`)
    .join("");
  $("#drawer").innerHTML = `
    <div class="drawer-head">
      <h3>${r.reference}</h3>
      <button class="close" id="drawer-close" aria-label="Fermer"><i data-lucide="x"></i></button>
    </div>
    <div style="margin:8px 0 14px"><span class="badge badge-soft">refusé</span>
      <span class="hint" style="display:inline-block;margin-left:6px">ligne ${r.index} du fichier — non scoré</span></div>
    <h3 style="margin-top:8px">Pourquoi ce dossier est refusé</h3>
    <table><thead><tr><th>champ</th><th>motif</th></tr></thead><tbody>${motifs}</tbody></table>
    <div class="note-art22">Corriger le champ en cause puis renvoyer le lot. Une cellule vide n'est pas une erreur : l'absence est imputée par le modèle.</div>`;
  $("#drawer-close").onclick = closeDrawer;
  $("#drawer").classList.add("open");
  $("#drawer-overlay").classList.add("open");
  refreshIcons();
}

function renderCampagne(host, res) {
  const s = res.synthese;
  const part = s.part_signalee == null ? null : s.part_signalee;
  const kpis = `<div class="kpis">
    <div class="kpi"><div class="v">${s.dossiers_recus}</div><div class="l">dossiers reçus</div></div>
    <div class="kpi"><div class="v">${s.dossiers_scores}</div><div class="l">scorés</div></div>
    <div class="kpi"><div class="v">${s.dossiers_refuses}</div><div class="l">refusés</div></div>
    <div class="kpi"><div class="v">${part == null ? "—" : fmtPct(part)}</div><div class="l">part signalée</div></div>
  </div>`;

  // Scorés et refusés cohabitent dans le tableau : la ligne refusée porte son motif, visible au clic.
  const scored = res.resultats.map((r, i) => ({
    __i: i,
    __refused: false,
    reference: r.reference_dossier,
    probability: r.proba_abandon,
    moyenne_finale: r.moyenne_finale,
    signaled: r.signaled,
    contributions_theme: r.contributions_theme,
    contributions_variable: r.contributions_variable,
  }));
  const refused = res.refuses.map((r, k) => ({
    __i: res.resultats.length + k,
    __refused: true,
    reference: r.reference_dossier ?? `ligne ${r.index}`,
    index: r.index,
    errors: r.erreurs,
    probability: null,
    moyenne_finale: null,
    signaled: null,
  }));

  CAMPAGNE = {
    rows: [...scored, ...refused],
    avertissement: res.avertissement,
    seuil: res.seuil_applique,
    provenance: res.provenance_seuil,
    derive: res.derive ?? null,
    scores: s.dossiers_scores,
    filter: "",
    signaledOnly: false,
    sortKey: null,
    sortDir: "desc",
    page: 1,
    pageSize: 50,
  };

  const th = (key, label, cls = "") =>
    `<th class="sortable ${cls}" data-key="${key}">${label} <span class="arrow">↕</span></th>`;
  const pageSizeOptions = PAGE_SIZES.map(
    (n) => `<option value="${n}"${n === CAMPAGNE.pageSize ? " selected" : ""}>${n}</option>`
  ).join("");

  const deriveTopHtml = res.derive ? deriveTop(res.derive) : "";

  host.innerHTML = `${deriveTopHtml}${kpis}
    <div class="card"><h3>Résultats de la campagne — cliquer une ligne pour le détail</h3>
      <div class="table-toolbar">
        <input class="search" id="camp-filter" placeholder="Filtrer par référence…" />
        <label class="muted"><input type="checkbox" id="camp-signaled" /> signalés seulement</label>
        <span class="grow"></span>
        <button class="btn btn-ghost" id="camp-export"><i data-lucide="download"></i> Exporter (CSV)</button>
      </div>
      <table><thead id="camp-thead"><tr>
        ${th("reference", "référence")}${th("probability", "proba abandon")}${th("moyenne_finale", "note /20")}${th("signaled", "indicateur")}
      </tr></thead><tbody id="camp-tbody"></tbody></table>
      <div class="pager">
        <span id="camp-count"></span><span class="grow"></span>
        <label class="muted">par page <select id="camp-pagesize">${pageSizeOptions}</select></label>
        <button class="btn btn-ghost" id="camp-prev">Précédent</button>
        <span id="camp-page"></span>
        <button class="btn btn-ghost" id="camp-next">Suivant</button>
      </div>
      <div class="note-art22">${res.avertissement}</div>
    </div>`;

  // Détail de la dérive : bouton du bandeau (ou lien discret si lot représentatif) → modale.
  const deriveDetail = $("#derive-detail");
  if (deriveDetail) {
    deriveDetail.onclick = (e) => {
      e.preventDefault();
      openDeriveModal();
    };
  }

  // Câblage (une fois) : filtre, signalés, export, taille de page, pagination.
  $("#camp-filter").oninput = (e) => {
    CAMPAGNE.filter = e.target.value;
    CAMPAGNE.page = 1;
    refreshCampagneTable();
  };
  $("#camp-signaled").onchange = (e) => {
    CAMPAGNE.signaledOnly = e.target.checked;
    CAMPAGNE.page = 1;
    refreshCampagneTable();
  };
  $("#camp-export").onclick = exportCampagne;
  $("#camp-pagesize").onchange = (e) => {
    CAMPAGNE.pageSize = Number(e.target.value);
    CAMPAGNE.page = 1;
    refreshCampagneTable();
  };
  $("#camp-prev").onclick = () => {
    CAMPAGNE.page -= 1;
    refreshCampagneTable();
  };
  $("#camp-next").onclick = () => {
    CAMPAGNE.page += 1;
    refreshCampagneTable();
  };

  // Tri : clic d'en-tête (délégation). Nouvelle colonne → sens par défaut (référence croissant, sinon décroissant).
  $("#camp-thead").onclick = (e) => {
    const th = e.target.closest("th.sortable");
    if (!th) return;
    const key = th.dataset.key;
    if (CAMPAGNE.sortKey === key) {
      CAMPAGNE.sortDir = CAMPAGNE.sortDir === "asc" ? "desc" : "asc";
    } else {
      CAMPAGNE.sortKey = key;
      CAMPAGNE.sortDir = key === "reference" ? "asc" : "desc";
    }
    refreshCampagneTable();
  };

  // Détail : clic d'une ligne (délégation) → tiroir latéral.
  $("#camp-tbody").onclick = (e) => {
    const tr = e.target.closest("tr[data-i]");
    if (!tr) return;
    const r = CAMPAGNE.rows.find((x) => x.__i === Number(tr.dataset.i));
    if (r) {
      openDossierPanel(r, {
        seuil: CAMPAGNE.seuil,
        provenance: CAMPAGNE.provenance,
        avertissement: CAMPAGNE.avertissement,
      });
    }
  };

  refreshCampagneTable();
  refreshIcons();
}

/* Bandeau de représentativité, en tête de campagne. Le message d'abord, la mécanique à la demande :
   orange en alerte, ambre léger à surveiller, un lien discret si le lot est représentatif. */
function deriveTop(d) {
  if (!d.mesurable) {
    return `<div class="hint" style="margin-bottom:16px">Dérive non mesurée : ${d.motif}.</div>`;
  }
  const psi = `PSI max ${fmtNum(d.psi_max, 3)}`;
  const bouton = `<button class="btn btn-ghost" id="derive-detail">Voir le détail</button>`;
  if (d.verdict === "alerte") {
    return `<div class="alert alert-warn" style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
      <div style="flex:1;min-width:220px"><strong>Dérive de représentativité</strong> — ce lot s'écarte nettement de la population sur laquelle le modèle a été entraîné (${psi}). Interpréter les scores avec prudence.</div>
      ${bouton}</div>`;
  }
  if (d.verdict === "à surveiller") {
    return `<div class="alert" style="background:var(--surface-2);border:1px solid var(--border);display:flex;align-items:center;gap:14px;flex-wrap:wrap">
      <div style="flex:1;min-width:220px"><strong>Représentativité à surveiller</strong> — écart modéré avec la population d'entraînement (${psi}), sans gravité immédiate.</div>
      ${bouton}</div>`;
  }
  // Lot représentatif : rien d'ostensible, juste un lien discret vers le détail.
  return `<div class="hint" style="margin-bottom:16px">Lot représentatif — <a href="#" id="derive-detail">voir le détail de la dérive</a></div>`;
}

/* Le tableau PSI/KS, réservé à la modale de détail. Le verdict est mis en rouge quand il alerte. */
function deriveTable(d) {
  const rows = d.variables
    .map((v) => {
      const cls = v.verdict === "alerte" ? ' class="verdict-alerte"' : "";
      return `<tr><td>${v.variable}</td><td>${fmtNum(v.psi, 3)}</td><td>${fmtNum(v.ks_pvalue, 3)}</td><td>${
        v.shift_std == null ? "—" : fmtNum(v.shift_std, 2) + " σ"
      }</td><td${cls}>${v.verdict}</td></tr>`;
    })
    .join("");
  return `<table><thead><tr><th>variable</th><th>PSI</th><th>p-value KS</th><th>déplacement</th><th>verdict</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

/* Modale de détail de la dérive : créée une fois, réutilisée. Fermée au clic hors-boîte ou sur Échap. */
function ensureModal() {
  if ($("#modal-overlay")) return;
  const overlay = el(`<div class="modal-overlay" id="modal-overlay"><div class="modal" id="modal" role="dialog" aria-modal="true"></div></div>`);
  document.body.appendChild(overlay);
  overlay.onclick = (e) => e.target === overlay && closeModal();
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeModal());
}
function closeModal() {
  $("#modal-overlay")?.classList.remove("open");
}

function openDeriveModal() {
  ensureModal();
  const d = CAMPAGNE.derive;
  const verdictColor = d.verdict === "alerte" ? "color:var(--danger)" : "";
  $("#modal").innerHTML = `
    <div class="drawer-head">
      <h3>Dérive du lot — verdict : <span style="${verdictColor}">${d.verdict}</span> (PSI max ${fmtNum(d.psi_max, 3)})</h3>
      <button class="close" id="modal-close" aria-label="Fermer"><i data-lucide="x"></i></button>
    </div>
    <p class="hint">Représentativité par rapport à la population d'entraînement. La décision se prend sur l'amplitude (PSI), pas sur la significativité (p-value du test KS). Bornes réglables par configuration.</p>
    ${deriveTable(d)}
    <div class="row-actions" style="margin-top:16px">
      <button class="btn btn-primary" id="derive-mail"><i data-lucide="mail"></i> Informer le support</button>
    </div>`;
  $("#modal-close").onclick = closeModal;
  $("#derive-mail").onclick = mailtoDerive;
  $("#modal-overlay").classList.add("open");
  refreshIcons();
}

/* Ouvre un brouillon de mail (sans destinataire — à renseigner) reprenant le tableau de dérive
   en texte : signalement actionnable au support, sans backend. */
function mailtoDerive() {
  const d = CAMPAGNE.derive;
  const sujet = `[Décrochage L1] Dérive ${d.verdict} — PSI max ${fmtNum(d.psi_max, 3)}`;
  const entete =
    `Signalement de dérive de représentativité — campagne de scoring décrochage L1\n\n` +
    `Verdict : ${d.verdict.toUpperCase()}\n` +
    `PSI max : ${fmtNum(d.psi_max, 3)}\n` +
    `Dossiers scorés : ${CAMPAGNE.scores}\n\n` +
    `Détail par variable (variable | PSI | p-value KS | déplacement | verdict) :\n`;
  const lignes = d.variables
    .map(
      (v) =>
        `- ${v.variable} | ${fmtNum(v.psi, 3)} | ${fmtNum(v.ks_pvalue, 3)} | ${
          v.shift_std == null ? "—" : fmtNum(v.shift_std, 2) + " σ"
        } | ${v.verdict}`
    )
    .join("\n");
  const corps = entete + lignes + `\n\nMessage généré depuis le client de démonstration.`;
  window.location.href = `mailto:?subject=${encodeURIComponent(sujet)}&body=${encodeURIComponent(corps)}`;
}

/* --- Écran : un dossier (formulaire STATIQUE) --- */
function screenDossier() {
  const content = $("#content");
  content.appendChild(
    el(`<div class="page-head"><h2>Examiner un dossier</h2>
      <p>Les valeurs sont normalisées avant envoi (nombres, modalités canoniques) ; le service valide, borne et score.</p></div>`)
  );

  // Champs regroupés par thématique — une section par thème, deux colonnes par section.
  const themes = [...new Set(CHAMPS.map((c) => c.theme))];
  const sections = themes
    .map((theme) => {
      const inputs = CHAMPS.filter((c) => c.theme === theme)
        .map(
          (c) => `<label class="field"><span class="lbl">${c.label} <span class="muted">${c.bornes}</span></span>
            <input data-col="${c.col}" placeholder="vide" /></label>`
        )
        .join("");
      return `<div class="theme-head">${theme}</div><div class="grid-form">${inputs}</div>`;
    })
    .join("");
  const selects = CATEGORIELLES.map((c) => {
    const options = c.options.map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
    return `<label class="field"><span class="lbl">${c.label}</span>
      <select data-col="${c.col}"><option value=""></option>${options}</select></label>`;
  }).join("");
  const contexte = `<div class="theme-head">Contexte</div><div class="grid-form">${selects}</div>`;

  const card = el(`<div class="card">
    ${sections}${contexte}
    <div class="row-actions">
      <button class="btn btn-primary" id="btn-estimer"><i data-lucide="activity"></i> Estimer</button>
      <button class="btn btn-ghost" id="btn-exemple">Remplir un exemple</button>
    </div>
  </div>`);
  content.appendChild(card);
  refreshIcons();

  const readForm = () => {
    const d = { reference_dossier: "demo-1" };
    card.querySelectorAll("[data-col]").forEach((n) => {
      if (n.value !== "") d[n.dataset.col] = n.value;
    });
    return cleanRow(d);
  };

  $("#btn-exemple").onclick = () => {
    card.querySelectorAll("[data-col]").forEach((n) => {
      if (DOSSIER_EXEMPLE[n.dataset.col] != null) n.value = DOSSIER_EXEMPLE[n.dataset.col];
    });
  };

  $("#btn-estimer").onclick = async () => {
    try {
      const seuilParam = State.seuil != null ? `?seuil=${State.seuil}` : "";
      const res = await api(`/v1/predict-etudiant${seuilParam}`, { method: "POST", body: readForm() });
      openDossierPanel(
        {
          reference: res.reference_dossier,
          probability: res.proba_abandon,
          moyenne_finale: res.moyenne_finale,
          signaled: res.signaled,
          contributions_theme: res.contributions_theme,
          contributions_variable: res.contributions_variable,
        },
        { seuil: res.seuil_applique, provenance: res.provenance_seuil, avertissement: res.avertissement }
      );
    } catch (e) {
      showError(e);
    }
  };
}

/* --- Écran : modèle (lit la fiche réelle du modèle servi via /v1/modele) --- */
function screenModele() {
  const content = $("#content");
  if (!State.fiche) {
    content.appendChild(el(`<div class="card"><p class="muted">Fiche indisponible — vérifier la clé d'API en Paramètres.</p></div>`));
    return;
  }
  const f = State.fiche;
  content.appendChild(el(`<div class="page-head"><h2>Fiche du modèle</h2><p>Version ${f.version} — telle que le service la publie.</p></div>`));

  // Variables regroupées par thème (la fiche porte la table variable -> thème).
  const parTheme = {};
  Object.entries(f.themes).forEach(([v, t]) => (parTheme[t] ??= []).push(v));
  const themeRows = Object.entries(parTheme)
    .map(([t, vs]) => `<tr><td>${t}</td><td>${vs.join(" · ")}</td></tr>`)
    .join("");
  content.appendChild(
    el(`<div class="card"><h3>Variables du modèle par thème</h3>
      <table><thead><tr><th>thème</th><th>variables</th></tr></thead><tbody>${themeRows}</tbody></table>
      <p class="muted" style="margin-top:8px">${f.numeric.length} numériques · ${f.categorical.length} catégorielles</p></div>`)
  );
  content.appendChild(
    el(`<div class="card"><h3>Exploitation</h3>
      <p>Seuil de décision par défaut : <strong>${fmtNum(f.seuil_defaut, 3)}</strong>.</p>
      <p class="muted">Dérive — surveiller ≥ ${fmtNum(f.derive.surveillance, 2)}, alerte ≥ ${fmtNum(f.derive.alerte, 2)} (effectif minimal ${f.derive.effectif_min}).</p>
      <p class="muted">Contrat d'entrée détaillé (types, bornes, modalités) : voir la
        <a href="${State.apiBase}/docs" target="_blank" rel="noopener">documentation OpenAPI</a>.</p></div>`)
  );
}

/* --- Écran : info (liens vers les surfaces techniques) --- */
function screenInfo() {
  const content = $("#content");
  content.appendChild(el(`<div class="page-head"><h2>Informations</h2><p>Surfaces techniques du dispositif.</p></div>`));
  const liens = [
    { t: "Documentation de l'API (Swagger UI)", u: State.apiBase + "/docs", i: "book-open" },
    { t: "Contrat OpenAPI (JSON)", u: State.apiBase + "/openapi.json", i: "file-json" },
    { t: "Supervision — Grafana", u: State.grafana, i: "line-chart" },
    { t: "Métriques — Prometheus", u: State.prometheus, i: "activity" },
  ];
  const items = liens
    .map(
      (l) => `<li style="margin:8px 0"><a href="${l.u}" target="_blank" rel="noopener">
        <i data-lucide="${l.i}" style="width:15px;height:15px;vertical-align:-2px"></i> ${l.t}</a>
        <span class="muted"> — ${l.u}</span></li>`
    )
    .join("");
  content.appendChild(el(`<div class="card"><ul style="list-style:none;padding:0;margin:0">${items}</ul></div>`));
  refreshIcons();
}

/* --- Écran : paramètres --- */
function screenParametres() {
  const content = $("#content");
  content.appendChild(el(`<div class="page-head"><h2>Paramètres</h2><p>Démonstrateur localhost : la clé est mémorisée dans ce navigateur.</p></div>`));
  const card = el(`<div class="card">
    <label class="field" style="margin-bottom:12px">adresse du service
      <input id="p-base" value="${State.apiBase}" /></label>
    <label class="field" style="margin-bottom:12px">clé d'API
      <input id="p-key" type="password" value="${State.apiKey}" placeholder="X-API-Key" /></label>
    <label class="field" style="margin-bottom:12px">URL Grafana
      <input id="p-grafana" value="${State.grafana}" /></label>
    <label class="field" style="margin-bottom:12px">URL Prometheus
      <input id="p-prom" value="${State.prometheus}" /></label>
    <div class="row-actions">
      <button class="btn btn-primary" id="p-save"><i data-lucide="save"></i> Enregistrer et tester</button>
    </div>
    <div class="hint" id="p-status"></div>
  </div>`);
  content.appendChild(card);
  refreshIcons();

  $("#p-save").onclick = async () => {
    State.apiBase = $("#p-base").value.trim().replace(/\/$/, "");
    State.apiKey = $("#p-key").value.trim();
    State.grafana = $("#p-grafana").value.trim().replace(/\/$/, "");
    State.prometheus = $("#p-prom").value.trim().replace(/\/$/, "");
    localStorage.setItem("dl1.apiBase", State.apiBase);
    localStorage.setItem("dl1.apiKey", State.apiKey);
    localStorage.setItem("dl1.grafana", State.grafana);
    localStorage.setItem("dl1.prometheus", State.prometheus);
    try {
      const seuil = await api("/v1/seuil");
      $("#p-status").textContent = `Clé acceptée. Seuil en vigueur : ${fmtNum(seuil.seuil, 3)} (${seuil.provenance}).`;
      await loadFiche();
      await refreshStatus();
    } catch (e) {
      $("#p-status").textContent = e.status === 401 ? "Clé refusée (401)." : `Échec (${e.status || "réseau"}).`;
    }
  };
}

function showError(e) {
  if (e.status === 422 && e.data && Array.isArray(e.data.detail)) {
    // 422 typé de FastAPI : liste d'erreurs {loc, msg}. Le dernier élément de `loc` nomme le champ.
    const champs = e.data.detail
      .map((x) => `${Array.isArray(x.loc) ? x.loc[x.loc.length - 1] : "champ"} — ${x.msg}`)
      .join(" · ");
    toast(`Refusé : ${champs}`, "danger");
  } else if (e.status === 401) {
    toast("Clé d'API absente ou invalide (voir Paramètres).", "danger");
  } else if (e.status === 503) {
    toast("Service ou modèle indisponible (503).", "danger");
  } else {
    toast(`Erreur ${e.status || "réseau"}.`, "danger");
  }
}

/* --- Écran : accueil (cartes cliquables vers les sections) --- */
function screenAccueil() {
  const content = $("#content");
  content.appendChild(
    el(`<div class="page-head"><h2>Bienvenue</h2>
      <p>Aide à la décision pour la détection précoce du décrochage en L1. Choisir une section.</p></div>`)
  );
  const cards = NAV.filter((n) => n.id !== "accueil")
    .map(
      (n) => `<button class="home-card" data-id="${n.id}">
        <span class="ic"><i data-lucide="${n.icon}"></i></span>
        <h3>${n.label}</h3><p>${n.desc}</p>
        <span class="go">Ouvrir <i data-lucide="arrow-right"></i></span>
      </button>`
    )
    .join("");
  const grid = el(`<div class="home-grid">${cards}</div>`);
  grid.querySelectorAll(".home-card").forEach((c) => (c.onclick = () => go(c.dataset.id)));
  content.appendChild(grid);
  refreshIcons();
}

/* --- Navigation --- */
const NAV = [
  { id: "accueil", label: "Accueil", icon: "home", screen: screenAccueil, desc: "" },
  {
    id: "campagne",
    label: "Campagne",
    icon: "users",
    screen: screenCampagne,
    desc: "Scorer une promotion entière depuis un fichier tabulaire : probabilités, note estimée, explicabilité et dérive.",
  },
  {
    id: "dossier",
    label: "Dossier",
    icon: "user",
    screen: screenDossier,
    desc: "Estimer le risque d'un étudiant et lire les facteurs qui pèsent, regroupés par thématique.",
  },
  {
    id: "modele",
    label: "Modèle",
    icon: "file-text",
    screen: screenModele,
    desc: "La fiche du modèle déployé : variables par thème, version et paramètres d'exploitation.",
  },
  {
    id: "info",
    label: "Info",
    icon: "info",
    screen: screenInfo,
    desc: "Surfaces techniques : documentation de l'API (Swagger), supervision Grafana et Prometheus.",
  },
  {
    id: "parametres",
    label: "Paramètres",
    icon: "settings",
    screen: screenParametres,
    desc: "Adresse du service, clé d'API et URLs de supervision.",
  },
];

function go(id) {
  const n = NAV.find((x) => x.id === id) || NAV[0];
  $("#nav")
    .querySelectorAll("button")
    .forEach((b) => b.classList.toggle("active", b.dataset.id === n.id));
  const bc = $("#breadcrumb");
  bc.innerHTML =
    n.id === "accueil"
      ? `<i data-lucide="home"></i> <span>Accueil</span>`
      : `<a id="bc-home"><i data-lucide="home"></i> Accueil</a> <span>/</span> <span>${n.label}</span>`;
  const home = $("#bc-home");
  if (home) home.onclick = () => go("accueil");
  $("#content").innerHTML = "";
  n.screen();
  refreshIcons();
}

function applyCollapsed(collapsed) {
  $("#app").classList.toggle("collapsed", collapsed);
  localStorage.setItem("dl1.collapsed", collapsed ? "1" : "0");
}

function init() {
  applyTheme(State.theme);
  const nav = $("#nav");
  NAV.forEach((n) => {
    const b = el(`<button data-id="${n.id}"><i data-lucide="${n.icon}"></i> <span>${n.label}</span></button>`);
    b.onclick = () => go(n.id);
    nav.appendChild(b);
  });
  $("#btn-params").onclick = () => go("parametres");
  $("#btn-home").onclick = () => go("accueil");
  $("#btn-theme").onclick = () => applyTheme(State.theme === "dark" ? "light" : "dark");
  applyCollapsed(localStorage.getItem("dl1.collapsed") === "1");
  $("#btn-collapse").onclick = () => applyCollapsed(!$("#app").classList.contains("collapsed"));
  refreshIcons();
  refreshStatus().then(loadFiche).then(() => go("accueil"));
  // Indicateur d'état rafraîchi périodiquement (l'API peut tomber ou redémarrer).
  setInterval(refreshStatus, 12000);
}

init();
