/* Maquette de présentation — vanilla JS, zéro dépendance de framework (Lucide en CDN).
   Aucune règle métier ici : la page relaie au service, qui valide, convertit, borne et score.
   Le formulaire, ses bornes et ses modalités sont générés depuis la fiche publiée par le
   service (/v1/modele) — rien n'est recopié. La clé d'API vit dans le navigateur
   (localStorage) : posture démo assumée, pour un usage localhost. */

const State = {
  apiBase: localStorage.getItem("dl1.apiBase") || "http://localhost:8000",
  apiKey: localStorage.getItem("dl1.apiKey") || "",
  fiche: null,
  seuil: null,
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

let toastTimer;
function toast(message) {
  const t = $("#toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3200);
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

/* --- Bandeau d'état : service joignable et prêt, seuil en vigueur --- */
async function refreshStatus() {
  const pill = $("#service-pill");
  const label = $("#service-label");
  pill.className = "pill";
  try {
    const ready = await api("/ready", { key: false });
    if (ready.ready) {
      pill.classList.add("ok");
      label.textContent = "service prêt";
      State.seuil = ready.seuil;
    } else {
      pill.classList.add("ko");
      label.textContent = "modèle indisponible";
    }
  } catch {
    pill.classList.add("ko");
    label.textContent = "service injoignable";
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

/* --- Écran : un dossier --- */
function screenDossier() {
  const content = $("#content");
  if (!State.fiche) {
    content.appendChild(
      el(`<div class="card"><p class="muted">Fiche du modèle indisponible — vérifier la clé d'API en Paramètres.</p></div>`)
    );
    return;
  }
  const f = State.fiche;
  content.appendChild(
    el(`<div class="page-head"><h2>Examiner un dossier</h2>
      <p>Champs et bornes lus dans le contrat publié par le service ; une écriture « sale » (52,4 %, « INFORMATIQUE ») est acceptée et normalisée par le service, pas par cette page.</p></div>`)
  );

  const fields = f.input_columns
    .map((col) => {
      const b = f.bounds[col];
      const bornes = b ? ` [${b.minimum} ; ${b.maximum}]` : "";
      if (f.categorical.includes(col)) {
        const opts = (f.nominal_modalities[col] || [])
          .map((m) => `<option value="${m}">${m}</option>`)
          .join("");
        return `<label class="field">${col}<select data-col="${col}"><option value=""></option>${opts}</select></label>`;
      }
      return `<label class="field">${col}<span class="muted">${bornes}</span>
        <input data-col="${col}" placeholder="${b ? "" : "vide = manquant"}" /></label>`;
    })
    .join("");

  const card = el(`<div class="card">
    <div class="grid-form">${fields}</div>
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
      nb_devoirs_total: "10",
      nb_devoirs_rendus: "6",
      retards_rendus: "3",
      motivation: "2",
      messages_forum: "1",
      connexions_lms_30j: "4",
      filiere: f.nominal_modalities.filiere ? f.nominal_modalities.filiere[0] : "",
    };
    card.querySelectorAll("[data-col]").forEach((n) => {
      if (ex[n.dataset.col] != null) n.value = ex[n.dataset.col];
    });
  };

  $("#btn-estimer").onclick = async () => {
    try {
      const seuilParam = State.seuil != null ? `?seuil=${State.seuil}` : "";
      const res = await api(`/v1/predict-etudiant${seuilParam}`, { method: "POST", body: readForm() });
      renderDossierResult($("#dossier-result"), res, readForm());
    } catch (e) {
      showError(e);
    }
  };
}

function renderDossierResult(host, res, dossier) {
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
  // Curseur de seuil : la probabilité ne bouge pas, seul l'indicateur bascule.
  void dossier;
}

/* --- Écran : une campagne --- */
function screenCampagne() {
  const content = $("#content");
  content.appendChild(
    el(`<div class="page-head"><h2>Scorer une campagne</h2>
      <p>Un fichier tabulaire, une ligne par étudiant. Chaque ligne est envoyée au service, qui la valide et la score — ou la refuse en nommant le champ en cause.</p></div>`)
  );
  const card = el(`<div class="card">
    <div class="row-actions" style="margin:0;align-items:center">
      <input type="file" id="csv" accept=".csv,.tsv,.txt" />
      <label class="muted"><input type="checkbox" id="derive" /> mesurer la dérive</label>
      <button class="btn btn-primary" id="btn-scorer"><i data-lucide="play"></i> Scorer la campagne</button>
    </div>
    <div class="hint" id="csv-info"></div>
  </div>`);
  content.appendChild(card);
  content.appendChild(el(`<div id="campagne-result"></div>`));
  refreshIcons();

  let rows = [];
  $("#csv").onchange = async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    rows = parseTable(await file.text());
    $("#csv-info").textContent = `${rows.length} lignes lues, ${Object.keys(rows[0] || {}).length} colonnes`;
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

/* --- Écran : modèle --- */
function screenModele() {
  const content = $("#content");
  if (!State.fiche) {
    content.appendChild(el(`<div class="card"><p class="muted">Fiche indisponible.</p></div>`));
    return;
  }
  const f = State.fiche;
  content.appendChild(el(`<div class="page-head"><h2>Fiche du modèle</h2><p>Version ${f.version}.</p></div>`));
  const excl = f.exclusions
    .map((e) => `<tr><td>${e.column}</td><td>${e.motif}</td></tr>`)
    .join("");
  content.appendChild(
    el(`<div class="card"><h3>Variables du modèle (${f.input_columns.length} collectées + ${f.derived_columns.length} dérivées)</h3>
      <p class="muted">${[...f.input_columns, ...f.derived_columns].join(" · ")}</p></div>`)
  );
  content.appendChild(
    el(`<div class="card"><h3>Colonnes exclues du périmètre, et pourquoi</h3>
      <table><thead><tr><th>colonne</th><th>motif</th></tr></thead><tbody>${excl}</tbody></table></div>`)
  );
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
    localStorage.setItem("dl1.apiBase", State.apiBase);
    localStorage.setItem("dl1.apiKey", State.apiKey);
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
    toast(`Refusé : ${champs}`);
  } else if (e.status === 401) {
    toast("Clé d'API absente ou invalide (voir Paramètres).");
  } else {
    toast(`Erreur ${e.status || "réseau"}.`);
  }
}

/* --- Navigation --- */
const NAV = [
  { id: "campagne", label: "Campagne", icon: "users", screen: screenCampagne },
  { id: "dossier", label: "Dossier", icon: "user", screen: screenDossier },
  { id: "modele", label: "Modèle", icon: "file-text", screen: screenModele },
  { id: "parametres", label: "Paramètres", icon: "settings", screen: screenParametres },
];

function go(id) {
  const nav = $("#nav");
  nav.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  $("#content").innerHTML = "";
  (NAV.find((n) => n.id === id) || NAV[0]).screen();
  refreshIcons();
}

function init() {
  const nav = $("#nav");
  NAV.forEach((n) => {
    const b = el(`<button data-id="${n.id}"><i data-lucide="${n.icon}"></i> ${n.label}</button>`);
    b.onclick = () => go(n.id);
    nav.appendChild(b);
  });
  $("#btn-params").onclick = () => go("parametres");
  refreshIcons();
  refreshStatus().then(loadFiche).then(() => go("campagne"));
}

init();
