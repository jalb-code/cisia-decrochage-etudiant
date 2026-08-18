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
   les colonnes d'entrée du contrat du modèle final (§9). Une valeur vide n'est pas envoyée. */
const CHAMPS = [
  { col: "taux_presence_pct", label: "Taux de présence", bornes: "[0 ; 100] %", theme: "Assiduité" },
  { col: "nb_devoirs_total", label: "Devoirs attendus", bornes: "[1 ; 50]", theme: "Assiduité" },
  { col: "nb_devoirs_rendus", label: "Devoirs rendus", bornes: "[0 ; 50]", theme: "Assiduité" },
  { col: "retards_rendus", label: "Rendus en retard", bornes: "[0 ; 50]", theme: "Assiduité" },
  { col: "connexions_lms_30j", label: "Connexions LMS (30 j)", bornes: "[0 ; 500]", theme: "Engagement" },
  { col: "heures_lms_total", label: "Heures sur le LMS", bornes: "[0 ; 1000]", theme: "Engagement" },
  { col: "ressources_consultees", label: "Ressources consultées", bornes: "[0 ; 2000]", theme: "Engagement" },
  { col: "messages_forum", label: "Messages forum", bornes: "[0 ; 500]", theme: "Engagement" },
  { col: "motivation", label: "Motivation", bornes: "[1 ; 5]", theme: "Ressenti" },
  { col: "satisfaction", label: "Satisfaction", bornes: "[1 ; 5]", theme: "Ressenti" },
  { col: "sentiment_appartenance", label: "Sentiment d'appartenance", bornes: "[1 ; 5]", theme: "Ressenti" },
];
const FILIERES = ["Biologie", "Droit", "Gestion", "Informatique", "Lettres", "Mathématiques", "Psychologie", "STAPS"];

/* Colonnes attendues d'un fichier de campagne (mêmes que le Dossier statique + filière). À
   synchroniser avec les input_columns du contrat. `reference_dossier` est facultative. */
const EXPECTED_COLUMNS = [...CHAMPS.map((c) => c.col), "filiere"];

const $ = (sel) => document.querySelector(sel);
const el = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};
const refreshIcons = () => window.lucide && window.lucide.createIcons();
const fmtPct = (x) => (x == null ? "—" : (x * 100).toFixed(1) + " %");
const fmtNum = (x, d = 2) => (x == null ? "—" : Number(x).toFixed(d));

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
  $("#seuil-label").textContent = State.seuil == null ? "seuil —" : `seuil ${State.seuil}`;
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
const themeItems = (c) => Object.entries(c.by_theme).map(([k, v]) => ({ key: k, contribution: v }));
const variableItems = (c) =>
  c.by_variable.map((v) => ({ key: v.variable, contribution: v.contribution }));

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
      <label class="muted"><input type="checkbox" id="derive" /> mesurer la dérive</label>
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
          <li>écriture « sale » acceptée (<code>52,4 %</code>, <code>INFORMATIQUE</code>) : le service convertit et borne ;</li>
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
      const res = await api(`/v1/predict-cohorte${derive}`, { method: "POST", body: { dossiers: rows } });
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
  const exemple = ["etu-001", "72 %", "4", "18", "40", "10", "6", "3", "1", "2", "3", "2", "Informatique"];
  const csv = cols.join(",") + "\n" + exemple.slice(0, cols.length).join(",") + "\n";
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

function renderCampagne(host, res) {
  const s = res.synthese;
  const part = s.part_signalee == null ? null : s.part_signalee;
  const garde =
    part != null && (part < 0.3 || part > 0.55)
      ? `<div class="alert alert-warn">Part signalée de ${fmtPct(part)}, hors de l'intervalle habituel [30 % ; 55 %] : contrôler la qualité du lot avant toute diffusion.</div>`
      : "";
  const kpis = `<div class="kpis">
    <div class="kpi"><div class="v">${s.dossiers_recus}</div><div class="l">dossiers reçus</div></div>
    <div class="kpi"><div class="v">${s.dossiers_scores}</div><div class="l">scorés</div></div>
    <div class="kpi"><div class="v">${s.dossiers_refuses}</div><div class="l">refusés</div></div>
    <div class="kpi"><div class="v">${part == null ? "—" : fmtPct(part)}</div><div class="l">part signalée</div></div>
  </div>`;

  const lignes = res.resultats
    .map((r, i) => {
      const sig =
        r.signaled == null
          ? "—"
          : r.signaled
            ? `<span class="badge badge-signale">signalé</span>`
            : `<span class="badge badge-non">non</span>`;
      const bars = contribBars(variableItems(r.contributions));
      return `<tr class="clickable" data-i="${i}"><td>${r.reference}</td><td>${fmtPct(r.probability)}</td>
        <td>${fmtNum(r.moyenne_finale, 1)}</td><td>${sig}</td></tr>
        <tr id="exp-${i}" hidden><td colspan="4">${bars}</td></tr>`;
    })
    .join("");

  const refus = res.refuses.length
    ? `<div class="card"><h3>Lignes refusées</h3><table><thead><tr><th>ligne</th><th>référence</th><th>motif</th></tr></thead><tbody>${res.refuses
        .map(
          (r) =>
            `<tr><td>${r.index}</td><td>${r.reference ?? ""}</td><td>${r.errors
              .map((e) => `${e.field} — ${e.message}`)
              .join(" · ")}</td></tr>`
        )
        .join("")}</tbody></table></div>`
    : "";

  const derive = res.derive ? renderDerive(res.derive) : "";

  host.innerHTML = `${kpis}${garde}
    <div class="card"><h3>Résultats — dans l'ordre du fichier (cliquer une ligne pour ses facteurs)</h3>
      <table><thead><tr><th>référence</th><th>proba abandon</th><th>note /20</th><th>indicateur</th></tr></thead>
      <tbody>${lignes}</tbody></table>
      <div class="note-art22">${res.avertissement}</div>
    </div>${derive}${refus}`;

  host.querySelectorAll("tr.clickable").forEach((tr) => {
    tr.onclick = () => {
      const exp = host.querySelector(`#exp-${tr.dataset.i}`);
      exp.hidden = !exp.hidden;
    };
  });
}

function renderDerive(d) {
  if (!d.mesurable) return `<div class="card"><h3>Dérive</h3><p class="muted">${d.motif}</p></div>`;
  const rows = d.variables
    .map(
      (v) =>
        `<tr><td>${v.variable}</td><td>${fmtNum(v.psi, 3)}</td><td>${fmtNum(v.ks_pvalue, 3)}</td><td>${
          v.shift_std == null ? "—" : fmtNum(v.shift_std, 2) + " σ"
        }</td><td>${v.verdict}</td></tr>`
    )
    .join("");
  return `<div class="card"><h3>Dérive de la campagne — verdict : ${d.verdict} (PSI max ${fmtNum(d.psi_max, 3)})</h3>
    <p class="hint">La décision se prend sur l'amplitude (PSI), pas sur la significativité (p-value du test KS).</p>
    <table><thead><tr><th>variable</th><th>PSI</th><th>p-value KS</th><th>déplacement</th><th>verdict</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

/* --- Écran : un dossier (formulaire STATIQUE) --- */
function screenDossier() {
  const content = $("#content");
  content.appendChild(
    el(`<div class="page-head"><h2>Examiner un dossier</h2>
      <p>Une écriture « sale » (52,4 %, « INFORMATIQUE ») est acceptée : c'est le service qui convertit, borne et score — pas cette page.</p></div>`)
  );

  // Champs regroupés par thématique — une section par thème, deux colonnes par section.
  const themes = [...new Set(CHAMPS.map((c) => c.theme))];
  const sections = themes
    .map((theme) => {
      const inputs = CHAMPS.filter((c) => c.theme === theme)
        .map(
          (c) => `<label class="field">${c.label} <span class="muted">${c.bornes}</span>
            <input data-col="${c.col}" placeholder="vide = manquant" /></label>`
        )
        .join("");
      return `<div class="theme-head">${theme}</div><div class="grid-form">${inputs}</div>`;
    })
    .join("");
  const options = FILIERES.map((m) => `<option value="${m}">${m}</option>`).join("");
  const contexte = `<div class="theme-head">Contexte</div><div class="grid-form">
    <label class="field">Filière
      <select data-col="filiere"><option value=""></option>${options}</select></label></div>`;

  const card = el(`<div class="card">
    ${sections}${contexte}
    <div class="row-actions">
      <button class="btn btn-primary" id="btn-estimer"><i data-lucide="activity"></i> Estimer</button>
      <button class="btn btn-ghost" id="btn-exemple">Remplir un exemple</button>
    </div>
    <div id="dossier-result"></div>
  </div>`);
  content.appendChild(card);
  refreshIcons();

  const readForm = () => {
    const d = { reference_dossier: "demo-1" };
    card.querySelectorAll("[data-col]").forEach((n) => {
      if (n.value !== "") d[n.dataset.col] = n.value;
    });
    return d;
  };

  $("#btn-exemple").onclick = () => {
    const ex = {
      taux_presence_pct: "72 %",
      connexions_lms_30j: "4",
      heures_lms_total: "18",
      ressources_consultees: "40",
      nb_devoirs_total: "10",
      nb_devoirs_rendus: "6",
      retards_rendus: "3",
      messages_forum: "1",
      motivation: "2",
      satisfaction: "3",
      sentiment_appartenance: "2",
      filiere: "Informatique",
    };
    card.querySelectorAll("[data-col]").forEach((n) => {
      if (ex[n.dataset.col] != null) n.value = ex[n.dataset.col];
    });
  };

  $("#btn-estimer").onclick = async () => {
    try {
      const seuilParam = State.seuil != null ? `?seuil=${State.seuil}` : "";
      const res = await api(`/v1/predict-etudiant${seuilParam}`, { method: "POST", body: readForm() });
      renderDossierResult($("#dossier-result"), res);
    } catch (e) {
      showError(e);
    }
  };
}

function renderDossierResult(host, res) {
  const r = res.resultat;
  const c = r.contributions;
  const signale =
    r.signaled == null
      ? ""
      : r.signaled
        ? `<span class="badge badge-signale">signalé</span>`
        : `<span class="badge badge-non">non signalé</span>`;
  host.innerHTML = `
    <hr style="border:0;border-top:1px solid var(--border);margin:16px 0" />
    <div class="stat-row">
      <div><div class="hint">probabilité d'abandon</div><div class="big-proba">${fmtPct(r.probability)}</div></div>
      <div><div class="hint">note finale estimée</div><div class="big-proba" style="font-size:28px">${fmtNum(r.moyenne_finale, 1)} / 20</div></div>
      <div>${signale}<div class="hint">seuil ${res.seuil_applique} (${res.provenance_seuil})</div></div>
    </div>
    <h3 style="margin-top:18px">Ce qui pèse sur cette estimation — par thème</h3>
    ${contribBars(themeItems(c))}
    <details style="margin-top:10px"><summary class="muted">détail par variable</summary>${contribBars(variableItems(c))}</details>
    <div class="note-art22">${res.avertissement}</div>`;
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
  content.appendChild(
    el(`<div class="card"><h3>Variables du modèle (${f.input_columns.length} collectées + ${f.derived_columns.length} dérivées)</h3>
      <p class="muted">${[...f.input_columns, ...f.derived_columns].join(" · ")}</p></div>`)
  );
  const excl = f.exclusions.map((e) => `<tr><td>${e.column}</td><td>${e.motif}</td></tr>`).join("");
  content.appendChild(
    el(`<div class="card"><h3>Colonnes exclues du périmètre, et pourquoi</h3>
      <table><thead><tr><th>colonne</th><th>motif</th></tr></thead><tbody>${excl}</tbody></table></div>`)
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
      $("#p-status").textContent = `Clé acceptée. Seuil en vigueur : ${seuil.seuil} (${seuil.provenance}).`;
      await loadFiche();
      await refreshStatus();
    } catch (e) {
      $("#p-status").textContent = e.status === 401 ? "Clé refusée (401)." : `Échec (${e.status || "réseau"}).`;
    }
  };
}

function showError(e) {
  if (e.status === 422 && e.data && e.data.detail && e.data.detail.errors) {
    const champs = e.data.detail.errors.map((x) => `${x.field} — ${x.message}`).join(" · ");
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
    desc: "La fiche du modèle déployé : variables, version, et colonnes exclues avec leur motif.",
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
