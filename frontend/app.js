/* Student Journey — minimal SPA (no framework, no build step).
 *
 * Talks to the FastAPI backend with a Bearer JWT kept in localStorage.
 * Change API_BASE if your backend isn't on http://localhost:8000.
 */

const API_BASE = localStorage.getItem("sj_api") || "http://localhost:8000";
const TOKEN_KEY = "sj_token";

// User-facing brand. Kept neutral so it speaks to students AND working
// professionals (the repo/codename stays "Student Journey"). Change here only.
const BRAND = "Journey";

// Inline SVG logo mark (an upward "growth" line) — neutral, more product-grade
// than an emoji. variant "light" is for dark/gradient backgrounds.
function logoMark(variant = "dark") {
  const rectFill = variant === "light" ? "#ffffff" : "url(#lg)";
  const stroke = variant === "light" ? "url(#lg)" : "#ffffff";
  const dot = variant === "light" ? "url(#lg)" : "#ffffff";
  return `<svg class="logo" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
    <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#6d5cf0"/><stop offset="1" stop-color="#4f7cf7"/>
    </linearGradient></defs>
    <rect width="32" height="32" rx="9" fill="${rectFill}"/>
    <path d="M8 21 L14 13 L19 18 L25 9" fill="none" stroke="${stroke}" stroke-width="2.6"
      stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="25" cy="9" r="2.3" fill="${dot}"/>
  </svg>`;
}

// ── tiny helpers ────────────────────────────────────────────────────────────
const app = document.getElementById("app");
const $ = (sel, root = document) => root.querySelector(sel);
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

let toastTimer;
function toast(msg, kind = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 3200);
}

// Escape user-provided strings before injecting into innerHTML.
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : "Request failed");
    this.status = status;
    this.detail = detail;
  }
}

async function api(path, { method = "GET", body, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) headers["Authorization"] = `Bearer ${getToken()}`;
  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, `Cannot reach the API at ${API_BASE}. Is the backend running?`);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && auth) {
      clearToken();
      go("#/signin");
    }
    throw new ApiError(res.status, errMessage(data));
  }
  return data;
}

// FastAPI errors are {detail: "..."} or 422 {detail: [{loc, msg}, ...]}.
function errMessage(data) {
  if (!data) return "Something went wrong.";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`)
      .join(" · ");
  }
  return "Something went wrong.";
}

// Wrap a submit button: show a spinner + disable while `fn` runs.
async function withLoading(btn, label, fn) {
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spin"></span> ${label}`;
  try {
    await fn();
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

function go(hash) {
  if (location.hash === hash) render();
  else location.hash = hash;
}

// ── a small "chips" editor (for skills / subjects / exams / topics) ─────────
function chipsInput(placeholder, initial = []) {
  const wrap = document.createElement("div");
  wrap.className = "chips";
  let values = [...initial];

  const input = document.createElement("input");
  input.placeholder = placeholder;

  function draw() {
    wrap.querySelectorAll(".chip").forEach((c) => c.remove());
    values.forEach((v, i) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `<b>${esc(v)}</b>`;
      const x = document.createElement("button");
      x.type = "button";
      x.textContent = "×";
      x.onclick = () => { values.splice(i, 1); draw(); };
      chip.appendChild(x);
      wrap.insertBefore(chip, input);
    });
  }

  function add() {
    const v = input.value.trim().replace(/,$/, "").trim();
    if (v && !values.includes(v)) values.push(v);
    input.value = "";
    draw();
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
    else if (e.key === "Backspace" && !input.value && values.length) { values.pop(); draw(); }
  });
  input.addEventListener("blur", add);

  wrap.appendChild(input);
  draw();
  return { el: wrap, get: () => values };
}

// ── views ───────────────────────────────────────────────────────────────────
function authShell(title, sub, formHtml, footerHtml) {
  app.innerHTML = `
    <div class="auth">
     <div class="auth__card">
      <aside class="auth__brand">
        <div class="brandmark">${logoMark("light")} ${BRAND}</div>
        <div>
          <span class="audience-pill">✦ For students & working professionals</span>
          <h1>A learning path built around you.</h1>
          <p class="lead">Whether you're preparing for exams or leveling up your career, we tailor the journey to your goals.</p>
        </div>
        <ul class="auth__features">
          <li><span class="ic">🧭</span><div><b>Personalized onboarding</b><span>Shaped by your background & goals</span></div></li>
          <li><span class="ic">📚</span><div><b>AI-curated material</b><span>The right resources, not endless lists</span></div></li>
          <li><span class="ic">📝</span><div><b>Quizzes & mock practice</b><span>Practice that adapts to you</span></div></li>
        </ul>
      </aside>
      <section class="auth__panel">
        <div class="card">
          <h2>${title}</h2>
          <p class="sub">${sub}</p>
          ${formHtml}
          <div class="alt">${footerHtml}</div>
        </div>
      </section>
     </div>
    </div>`;
}

function renderSignin() {
  authShell(
    "Welcome back",
    "Sign in to continue your journey.",
    `<form id="form">
      <div class="field">
        <label>Email</label>
        <input name="email" type="email" autocomplete="email" required placeholder="you@example.com" />
      </div>
      <div class="field">
        <label>Password</label>
        <input name="password" type="password" autocomplete="current-password" required placeholder="••••••••" />
      </div>
      <div class="error-text" id="err"></div>
      <button class="btn btn-primary btn-block" type="submit">Sign in</button>
    </form>`,
    `New here? <a href="#/signup">Create an account</a>`
  );

  $("#form").addEventListener("submit", (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    const f = e.target;
    withLoading(f.querySelector("button"), "Signing in…", async () => {
      try {
        const { access_token } = await api("/auth/login", {
          method: "POST",
          body: { email: f.email.value.trim(), password: f.password.value },
        });
        setToken(access_token);
        await routeAfterAuth();
      } catch (err) {
        $("#err").textContent = err.message;
      }
    });
  });
}

function renderSignup() {
  authShell(
    "Create your account",
    "Start your personalized learning journey.",
    `<form id="form">
      <div class="field">
        <label>Full name <span class="hint">(optional)</span></label>
        <input name="full_name" autocomplete="name" placeholder="Ada Lovelace" />
      </div>
      <div class="field">
        <label>Email</label>
        <input name="email" type="email" autocomplete="email" required placeholder="you@example.com" />
      </div>
      <div class="field">
        <label>Password <span class="hint">(min 8 characters)</span></label>
        <input name="password" type="password" autocomplete="new-password" required minlength="8" placeholder="••••••••" />
      </div>
      <div class="error-text" id="err"></div>
      <button class="btn btn-primary btn-block" type="submit">Create account</button>
    </form>`,
    `Already have an account? <a href="#/signin">Sign in</a>`
  );

  $("#form").addEventListener("submit", (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    const f = e.target;
    const email = f.email.value.trim();
    const password = f.password.value;
    withLoading(f.querySelector("button"), "Creating…", async () => {
      try {
        // 1. create the account
        const created = await api("/auth/signup", {
          method: "POST",
          body: { email, password, full_name: f.full_name.value.trim() || null },
        });
        // 2. dev convenience: email sending lands in Phase 5, so verify with the
        //    token the API just handed us. Harmless if it's already gone.
        if (created.email_verification_token) {
          try {
            await api("/auth/verify-email", {
              method: "POST",
              body: { token: created.email_verification_token },
            });
          } catch (_) {}
        }
        // 3. log straight in and continue to onboarding
        const { access_token } = await api("/auth/login", {
          method: "POST",
          body: { email, password },
        });
        setToken(access_token);
        toast("Account created — let's set you up!", "ok");
        await routeAfterAuth();
      } catch (err) {
        $("#err").textContent = err.message;
      }
    });
  });
}

// The after-login shell mirrors the auth split card: a gradient sidebar (brand +
// nav + user) on the left, frosted content on the right, all in one floating card.
function appShell(active, inner) {
  const u = state.user || {};
  const name = (u.full_name || u.email || "there").split("@")[0];
  const initials = (u.full_name || u.email || "?").trim()[0].toUpperCase();
  const showPredictor = hasPredictorExam(state.profile);
  // Profile & preferences are edited from the dashboard, not permanent tabs.
  // The sidebar shows "home" plus what's coming next in the journey.
  return `
    <div class="layout">
      <div class="layout__card">
        <aside class="sidebar">
          <div class="brandmark">${logoMark("light")} ${BRAND}</div>
          <nav class="nav">
            <a href="#/dashboard" class="nav__item ${active === "dashboard" ? "on" : ""}"><span class="nav__ic">🏠</span>Dashboard</a>
            <a href="#/study" class="nav__item ${active === "study" ? "on" : ""}"><span class="nav__ic">📚</span>Study material</a>
            <a href="#/quizzes" class="nav__item ${active === "quizzes" ? "on" : ""}"><span class="nav__ic">📝</span>Quizzes &amp; tests</a>
            <a href="#/mock-tests" class="nav__item ${active === "mock" ? "on" : ""}"><span class="nav__ic">📋</span>Mock tests</a>
            <a href="#/courses" class="nav__item ${active === "courses" ? "on" : ""}"><span class="nav__ic">🎓</span>Courses</a>
            <div class="nav__label">Explore</div>
            <a href="${FMC_TOOLS.courseFinder}" target="_blank" rel="noopener noreferrer" class="nav__item"><span class="nav__ic">🔍</span>Find a course ↗</a>
            ${showPredictor ? `<a href="${FMC_TOOLS.cutoffPredictor}" target="_blank" rel="noopener noreferrer" class="nav__item"><span class="nav__ic">🎯</span>College predictor ↗</a>` : ""}
            ${u.role === "admin" ? `<div class="nav__label">Admin</div>
            <a href="#/admin" class="nav__item ${active === "admin" ? "on" : ""}"><span class="nav__ic">🛠️</span>Manage courses</a>` : ""}
          </nav>
          <div class="sidebar__foot">
            <div class="sidebar__user">
              <div class="avatar">${esc(initials)}</div>
              <div class="sidebar__meta"><b>${esc(name)}</b><span>${esc(u.email || "")}</span></div>
            </div>
            <button class="btn btn-ghost btn-block" id="logout">Log out</button>
          </div>
        </aside>
        <main class="content"><div class="content__scroll">${inner}</div></main>
      </div>
    </div>`;
}

function wireShell() {
  const btn = $("#logout");
  if (btn) btn.onclick = () => { clearToken(); state = {}; go("#/signin"); };
}

function renderOnboarding() {
  const existingType = state.user?.user_type || null;
  let chosen = existingType;

  const editing = !!state.user?.user_type;
  app.innerHTML = appShell(
    null,
    `${editing ? `<a class="back" href="#/dashboard">← Dashboard</a>` : ""}
      <div class="section-head">
        <h2>Tell us about yourself</h2>
        <p>This shapes the study material and tests we'll build for you.</p>
      </div>
      <div class="type-grid" id="types">
        <button class="type-card ${chosen === "student" ? "on" : ""}" data-type="student">
          <span class="check">✓</span>
          <div class="emoji">🎓</div><h3>Student</h3>
          <p>Schooling, streams, subjects, target exams & dream colleges.</p>
        </button>
        <button class="type-card ${chosen === "professional" ? "on" : ""}" data-type="professional">
          <span class="check">✓</span>
          <div class="emoji">💼</div><h3>Working professional</h3>
          <p>Experience, role, industry, skills & where you're headed.</p>
        </button>
      </div>
      <div id="branch"></div>`
  );
  wireShell();

  const branch = $("#branch");
  const renderBranch = () => {
    branch.innerHTML = chosen === "student" ? studentFormHtml() : professionalFormHtml();
    chosen === "student" ? wireStudentForm() : wireProfessionalForm();
  };

  $("#types").querySelectorAll(".type-card").forEach((card) => {
    card.onclick = () => {
      chosen = card.dataset.type;
      $("#types").querySelectorAll(".type-card").forEach((c) => c.classList.toggle("on", c === card));
      renderBranch();
    };
  });

  if (chosen) renderBranch();
}

// ── findmycollege tools (org-owned, deep-linked) ────────────────────────────────
// Sibling products on findmycollege.com. For now we deep-link (open in a new tab);
// prefill query params can be appended once their URL contract is confirmed — e.g.
// course finder ?stream=/level=, predictor ?exam=/rank=/category= from the profile.
const FMC_TOOLS = {
  courseFinder: "https://findmycollege.com/course-finder",
  cutoffPredictor: "https://findmycollege.com/cutoff-predictor",
};
// Entrance exams we can hand off to the cutoff predictor — gates the predictor
// entry points so non-exam learners aren't shown an irrelevant tool.
const PREDICTOR_EXAMS = ["jee", "neet", "cuet", "bitsat", "gate", "cat", "viteee", "comedk", "wbjee"];
function hasPredictorExam(profile) {
  return (profile?.target_exams || []).some((e) => {
    const x = String(e).toLowerCase();
    return PREDICTOR_EXAMS.some((k) => x.includes(k));
  });
}

// Per-education-level field config. The form re-renders these when the learner
// picks a level so the inputs (and what the AI later studies/quizzes on) match
// where they actually are. `details.*` keys are stored in the profile's jsonb
// `details` map; plain keys reuse the dedicated columns. Mirrors 0008 migration.
const STUDENT_LEVEL_FIELDS = {
  high_school: [
    { key: "stream", type: "text", label: "Stream / Grade", hint: "e.g. 11th Grade Science", ph: "11th Grade Science / Class 10" },
    { key: "subjects", type: "chips", label: "Subjects you want to study", ph: "Add a subject…" },
    { key: "target_exams", type: "chips", label: "Target exams", hint: "SAT, ACT, JEE, NEET, Boards", ph: "Add an exam…" },
    { key: "preferred_colleges", type: "chips", label: "Dream colleges / universities", ph: "Add a college…", helper: { icon: "🎯", text: "Not sure what's realistic? Predict colleges from your rank", href: FMC_TOOLS.cutoffPredictor } },
  ],
  undergraduate: [
    { key: "details.degree", type: "text", label: "Degree / Major", ph: "B.Tech Computer Science / B.Com" },
    { key: "details.current_year", type: "select", label: "Current year", options: ["1st", "2nd", "3rd", "4th", "4th+"] },
    { key: "subjects", type: "chips", label: "Core subjects / skills to focus on", ph: "Add a subject or skill…" },
    { key: "details.future_pathway", type: "text", label: "Future pathway", hint: "Placements, Higher Studies, UPSC", ph: "Placements / Higher Studies / UPSC" },
  ],
  postgraduate: [
    { key: "details.specialization", type: "text", label: "Specialization", ph: "Data Science / MBA Marketing" },
    { key: "details.current_phase", type: "select", label: "Current phase", options: ["Coursework", "Thesis/Research", "Final Semester"] },
    { key: "target_exams", type: "chips", label: "Target certifications / competitive exams", hint: "NET, GATE, CFA", ph: "Add a certification or exam…" },
    { key: "details.target_industry", type: "text", label: "Target industry / goal", ph: "FinTech / Academia / R&D" },
  ],
  other: [
    { key: "details.current_focus", type: "text", label: "Current focus", hint: "Self-learning, Bootcamps, Certifications", ph: "Self-learning / Bootcamp" },
    { key: "details.field_of_interest", type: "text", label: "Primary field of interest", ph: "Software / Design / Finance" },
    { key: "details.knowledge_level", type: "select", label: "Current knowledge level", options: ["Beginner", "Intermediate", "Advanced"] },
    { key: "details.ultimate_goal", type: "text", label: "Your ultimate goal", ph: "Build a portfolio / Clear a certification" },
  ],
};

function studentFieldValue(p, key) {
  if (key.startsWith("details.")) return (p.details || {})[key.slice(8)] || "";
  return p[key] || "";
}

function studentFieldHtml(p, f) {
  const val = studentFieldValue(p, f.key);
  const hint = f.hint ? ` <span class="hint">(${f.hint})</span>` : "";
  const helper = f.helper
    ? `<p class="hint" style="margin-top:6px"><a href="${f.helper.href}" target="_blank" rel="noopener noreferrer">${f.helper.icon || ""} ${f.helper.text} →</a></p>`
    : "";
  let control;
  if (f.type === "chips") {
    control = `<div data-chips="${f.key}"></div>`;
  } else if (f.type === "select") {
    const opts = ["", ...f.options]
      .map((o) => `<option value="${esc(o)}" ${o === val ? "selected" : ""}>${o || "Select…"}</option>`)
      .join("");
    control = `<select data-field="${f.key}">${opts}</select>`;
  } else {
    control = `<input data-field="${f.key}" value="${esc(val)}" placeholder="${esc(f.ph || "")}" />`;
  }
  return `<div class="field"><label>${f.label}${hint}</label>${control}${helper}</div>`;
}

function studentFormHtml() {
  const p = state.profile && state.user?.user_type === "student" ? state.profile : {};
  return `
    <div class="panel">
      <form id="pform">
        <div class="field">
          <label>Education level</label>
          <select name="education_level" id="eduLevel">
            ${["", "high_school", "undergraduate", "postgraduate", "other"]
              .map((v) => `<option value="${v}" ${p.education_level === v ? "selected" : ""}>${v ? labelize(v) : "Select…"}</option>`)
              .join("")}
          </select>
        </div>
        <div id="studentFields"></div>
        <div class="error-text" id="err"></div>
        <div class="actions">
          <button class="btn btn-primary" type="submit">Save & continue →</button>
        </div>
      </form>
    </div>`;
}

function professionalFormHtml() {
  const p = state.profile && state.user?.user_type === "professional" ? state.profile : {};
  return `
    <div class="panel">
      <form id="pform">
        <div class="row2">
          <div class="field">
            <label>Years of experience</label>
            <input name="experience_years" type="number" min="0" max="80" value="${p.experience_years ?? ""}" placeholder="3" />
          </div>
          <div class="field">
            <label>Current role</label>
            <input name="role" value="${esc(p.role || "")}" placeholder="Backend Engineer" />
          </div>
        </div>
        <div class="field">
          <label>Industry</label>
          <input name="industry" value="${esc(p.industry || "")}" placeholder="Fintech" />
        </div>
        <div class="field"><label>Skills</label><div id="skills"></div></div>
        <div class="field">
          <label>Your goal</label>
          <textarea name="goal" placeholder="e.g. Move into a tech lead role within a year">${esc(p.goal || "")}</textarea>
        </div>
        <div class="error-text" id="err"></div>
        <div class="actions">
          <button class="btn btn-primary" type="submit">Save & continue →</button>
        </div>
      </form>
    </div>`;
}

function wireStudentForm() {
  const p = state.profile && state.user?.user_type === "student" ? state.profile : {};
  // chips instances for the currently-rendered level, keyed by field key.
  let chips = {};

  const renderFields = (level) => {
    chips = {};
    const fields = STUDENT_LEVEL_FIELDS[level];
    const host = $("#studentFields");
    if (!fields) {
      host.innerHTML = `<p class="hint" style="padding:4px 2px">Pick an education level to continue.</p>`;
      return;
    }
    // First two fields side-by-side, the rest stacked — keeps the form compact.
    host.innerHTML =
      `<div class="row2">${studentFieldHtml(p, fields[0])}${studentFieldHtml(p, fields[1])}</div>` +
      fields.slice(2).map((f) => studentFieldHtml(p, f)).join("");
    // Mount chips inputs where placeholders were rendered.
    fields
      .filter((f) => f.type === "chips")
      .forEach((f) => {
        const c = chipsInput(f.ph || "Add…", p[f.key] || []);
        host.querySelector(`[data-chips="${f.key}"]`).appendChild(c.el);
        chips[f.key] = c;
      });
  };

  renderFields($("#eduLevel").value);
  $("#eduLevel").addEventListener("change", (e) => renderFields(e.target.value));

  $("#pform").addEventListener("submit", (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    const f = e.target;
    const level = $("#eduLevel").value;
    if (!level) {
      $("#err").textContent = "Please pick an education level.";
      return;
    }
    // Collect the level's fields into columns vs the `details` jsonb map.
    const body = {
      user_type: "student",
      education_level: level,
      stream: null,
      subjects: [],
      target_exams: [],
      preferred_colleges: [],
      details: {},
    };
    STUDENT_LEVEL_FIELDS[level].forEach((fld) => {
      const toDetails = fld.key.startsWith("details.");
      const name = toDetails ? fld.key.slice(8) : fld.key;
      if (fld.type === "chips") {
        body[name] = chips[fld.key].get();
      } else {
        const el = $(`#studentFields [data-field="${fld.key}"]`);
        const val = (el?.value || "").trim();
        if (toDetails) {
          if (val) body.details[name] = val;
        } else {
          body[name] = val || null;
        }
      }
    });

    withLoading(f.querySelector("button"), "Saving…", async () => {
      try {
        await api("/users/me/profile", { method: "PUT", auth: true, body });
        await loadState();
        toast("Profile saved", "ok");
        go("#/preferences");
      } catch (err) {
        $("#err").textContent = err.message;
      }
    });
  });
}

function wireProfessionalForm() {
  const p = state.profile && state.user?.user_type === "professional" ? state.profile : {};
  const skills = chipsInput("Add a skill…", p.skills || []);
  $("#skills").appendChild(skills.el);

  $("#pform").addEventListener("submit", (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    const f = e.target;
    withLoading(f.querySelector("button"), "Saving…", async () => {
      try {
        await api("/users/me/profile", {
          method: "PUT",
          auth: true,
          body: {
            user_type: "professional",
            experience_years: f.experience_years.value === "" ? null : Number(f.experience_years.value),
            role: f.role.value.trim() || null,
            industry: f.industry.value.trim() || null,
            skills: skills.get(),
            goal: f.goal.value.trim() || null,
          },
        });
        await loadState();
        toast("Profile saved", "ok");
        go("#/preferences");
      } catch (err) {
        $("#err").textContent = err.message;
      }
    });
  });
}

function renderPreferences() {
  const p = state.preferences || {};
  let cadence = p.cadence || "none";
  let difficulty = p.difficulty || "";

  const editing = !!state.preferences;
  app.innerHTML = appShell(
    null,
    `${editing ? `<a class="back" href="#/dashboard">← Dashboard</a>` : ""}
      <div class="section-head">
        <h2>Your learning preferences</h2>
        <p>Tune how we curate material and schedule your practice.</p>
      </div>
      <div class="panel">
        <form id="pform">
          <div class="field"><label>Topics you want to focus on</label><div id="topics"></div></div>
          <div class="field">
            <label>Goal <span class="hint">(optional)</span></label>
            <input name="goal" value="${esc(p.goal || "")}" placeholder="e.g. Crack JEE / Prepare for interviews" />
          </div>
          <div class="row2">
            <div class="field">
              <label>Practice cadence</label>
              <div class="segmented" id="cadence">
                ${seg(["none", "daily", "weekly"], cadence)}
              </div>
            </div>
            <div class="field">
              <label>Difficulty</label>
              <div class="segmented" id="difficulty">
                ${seg(["beginner", "intermediate", "advanced"], difficulty)}
              </div>
            </div>
          </div>
          <div class="field">
            <label class="toggle">
              <input type="checkbox" id="notif" ${p.notifications_enabled === false ? "" : "checked"} />
              <span class="track"></span>
              <span>Email me reminders & results</span>
            </label>
          </div>
          <div class="error-text" id="err"></div>
          <div class="actions">
            <button class="btn btn-ghost" type="button" id="skip">Skip for now</button>
            <button class="btn btn-primary" type="submit">Save preferences →</button>
          </div>
        </form>
      </div>`
  );
  wireShell();

  const topics = chipsInput("Add a topic…", p.topics || []);
  $("#topics").appendChild(topics.el);

  segWire("#cadence", (v) => (cadence = v));
  segWire("#difficulty", (v) => (difficulty = v), true);

  $("#skip").onclick = () => go("#/dashboard");

  $("#pform").addEventListener("submit", (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    const f = e.target;
    withLoading(f.querySelector("button"), "Saving…", async () => {
      try {
        await api("/preferences/me", {
          method: "PUT",
          auth: true,
          body: {
            topics: topics.get(),
            goal: f.goal.value.trim() || null,
            cadence,
            difficulty: difficulty || null,
            notifications_enabled: $("#notif").checked,
          },
        });
        await loadState();
        toast("Preferences saved", "ok");
        go("#/dashboard");
      } catch (err) {
        $("#err").textContent = err.message;
      }
    });
  });
}

function seg(options, current) {
  return options
    .map((o) => `<button type="button" data-v="${o}" class="${o === current ? "on" : ""}">${labelize(o)}</button>`)
    .join("");
}
function segWire(sel, onPick, allowToggleOff = false) {
  const group = $(sel);
  group.querySelectorAll("button").forEach((b) => {
    b.onclick = () => {
      const already = b.classList.contains("on");
      group.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
      if (allowToggleOff && already) { onPick(""); return; }
      b.classList.add("on");
      onPick(b.dataset.v);
    };
  });
}

function renderDashboard() {
  const u = state.user || {};
  const prof = state.profile;
  const prefs = state.preferences;
  const name = (u.full_name || u.email || "there").split("@")[0];
  const tagline =
    u.user_type === "professional"
      ? "Your upskilling journey, all in one place."
      : u.user_type === "student"
        ? "Your study journey, all in one place."
        : "Let's finish setting up your profile.";

  app.innerHTML = appShell(
    "dashboard",
    `<div class="welcome">
        <div>
          <h2>Welcome${u.full_name ? " back" : ""}, ${esc(name)} 👋</h2>
          <p>${tagline}</p>
        </div>
        <span class="badge ${u.is_email_verified ? "badge--ok" : "badge--warn"}">${u.is_email_verified ? "✓ Email verified" : "● Not verified"}</span>
      </div>

      <div class="panel">
        <div class="panel__head">
          <h3>Your profile</h3>
          <button class="btn btn-ghost" id="editProfile">Edit</button>
        </div>
        ${prof ? profileSummary(u.user_type, prof) : `<p class="empty">No profile yet — add one to personalize your journey.</p>`}
      </div>

      <div class="panel">
        <div class="panel__head">
          <h3>Learning preferences</h3>
          <button class="btn btn-ghost" id="editPrefs">Edit</button>
        </div>
        ${prefs ? prefsSummary(prefs) : `<p class="empty">No preferences set yet.</p>`}
      </div>

      <div class="panel">
        <div class="panel__head">
          <h3>Study material</h3>
          <button class="btn btn-ghost" id="goStudy">Open</button>
        </div>
        <p class="empty" style="font-style:normal">📚 AI-curated reading, picked for your topics. Generate a fresh set and save the best to your library.</p>
        <div class="actions" style="justify-content:flex-start">
          <button class="btn btn-primary" id="goStudy2">Browse study material →</button>
        </div>
      </div>

      <div class="panel">
        <div class="panel__head">
          <h3>Quizzes &amp; tests</h3>
          <button class="btn btn-ghost" id="goQuiz">Open</button>
        </div>
        <p class="empty" style="font-style:normal">📝 Test yourself with AI-generated MCQs on your topics — instant scoring, explanations, and per-topic progress.</p>
        <div class="actions" style="justify-content:flex-start">
          <button class="btn btn-primary" id="goQuiz2">Take a quiz →</button>
        </div>
      </div>

      <div class="panel">
        <div class="panel__head">
          <h3>Mock tests 📋</h3>
          <button class="btn btn-ghost" id="goMock">Open</button>
        </div>
        <p class="empty" style="font-style:normal">📋 Sit a full-length, sectional, timed mock exam. Get a detailed report — section scores, percentile, time analysis and weak areas to focus on next.</p>
        <div class="actions" style="justify-content:flex-start">
          <button class="btn btn-primary" id="goMock2">Take a mock test →</button>
        </div>
      </div>

      <div class="panel">
        <div class="panel__head">
          <h3>Courses &amp; certifications</h3>
          <button class="btn btn-ghost" id="goCourses">Open</button>
        </div>
        <p class="empty" style="font-style:normal">🎓 Structured courses with lessons. Enrol, track progress, and earn a certificate — your syllabus also powers tailored study material &amp; quizzes.</p>
        <div class="actions" style="justify-content:flex-start">
          <button class="btn btn-primary" id="goCourses2">Browse courses →</button>
        </div>
      </div>

      <div class="panel">
        <div class="panel__head">
          <h3>Find your course 🔍</h3>
          <a class="btn btn-ghost" href="${FMC_TOOLS.courseFinder}" target="_blank" rel="noopener noreferrer">Open ↗</a>
        </div>
        <p class="empty" style="font-style:normal">🔍 Explore programs, degrees &amp; colleges across the country with our Course Finder — filter by stream, level and interest to discover where to study next.</p>
        <div class="actions" style="justify-content:flex-start">
          <a class="btn btn-primary" href="${FMC_TOOLS.courseFinder}" target="_blank" rel="noopener noreferrer">Find a course ↗</a>
        </div>
      </div>
      ${hasPredictorExam(prof) ? `
      <div class="panel">
        <div class="panel__head">
          <h3>College predictor 🎯</h3>
          <a class="btn btn-ghost" href="${FMC_TOOLS.cutoffPredictor}" target="_blank" rel="noopener noreferrer">Open ↗</a>
        </div>
        <p class="empty" style="font-style:normal">🎯 You're targeting ${esc((prof.target_exams || []).join(", "))}. Enter your rank or percentile in our Cutoff Predictor to see which colleges &amp; branches you can realistically get.</p>
        <div class="actions" style="justify-content:flex-start">
          <a class="btn btn-primary" href="${FMC_TOOLS.cutoffPredictor}" target="_blank" rel="noopener noreferrer">Predict my colleges ↗</a>
        </div>
      </div>` : ""}`
  );
  wireShell();
  $("#editProfile").onclick = () => go("#/onboarding");
  $("#editPrefs").onclick = () => go("#/preferences");
  $("#goStudy").onclick = () => go("#/study");
  $("#goStudy2").onclick = () => go("#/study");
  $("#goQuiz").onclick = () => go("#/quizzes");
  $("#goQuiz2").onclick = () => go("#/quizzes");
  $("#goMock").onclick = () => go("#/mock-tests");
  $("#goMock2").onclick = () => go("#/mock-tests");
  $("#goCourses").onclick = () => go("#/courses");
  $("#goCourses2").onclick = () => go("#/courses");
}

function profileSummary(type, p) {
  let rows;
  if (type === "student") {
    rows = [["Education", p.education_level ? labelize(p.education_level) : null]];
    // Show exactly the fields the learner filled for their level (matches the form).
    const fields = STUDENT_LEVEL_FIELDS[p.education_level] || [];
    fields.forEach((f) => {
      const v = f.type === "chips" ? taglist(p[f.key]) : studentFieldValue(p, f.key);
      rows.push([f.label, v || null]);
    });
  } else {
    rows = [
      ["Experience", p.experience_years != null ? `${p.experience_years} yrs` : null],
      ["Role", p.role],
      ["Industry", p.industry],
      ["Skills", taglist(p.skills)],
      ["Goal", p.goal],
    ];
  }
  return `<dl class="kv">${rows
    .map(([k, v]) => `<dt>${k}</dt><dd>${v || '<span class="empty">—</span>'}</dd>`)
    .join("")}</dl>`;
}

function prefsSummary(p) {
  const rows = [
    ["Topics", taglist(p.topics)],
    ["Goal", p.goal],
    ["Cadence", labelize(p.cadence)],
    ["Difficulty", p.difficulty ? labelize(p.difficulty) : null],
    ["Notifications", p.notifications_enabled ? "On" : "Off"],
  ];
  return `<dl class="kv">${rows
    .map(([k, v]) => `<dt>${k}</dt><dd>${v || '<span class="empty">—</span>'}</dd>`)
    .join("")}</dl>`;
}

function taglist(arr) {
  if (!arr || !arr.length) return "";
  return `<div class="taglist">${arr.map((x) => `<span>${esc(x)}</span>`).join("")}</div>`;
}

function labelize(s) {
  return String(s).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── study material ────────────────────────────────────────────────────────────
let studyTab = "feed"; // "feed" | "library"

const KIND_ICON = {
  docs: "📄", article: "📰", video: "🎬", course: "🎓", tutorial: "🧩", other: "🔗",
};

function resourceCard(r, { saved }) {
  const tags = (r.tags && r.tags.length)
    ? `<div class="taglist">${r.tags.slice(0, 5).map((t) => `<span>${esc(t)}</span>`).join("")}</div>`
    : "";
  const meta = [
    r.source_domain ? esc(r.source_domain) : null,
    r.est_minutes ? `${r.est_minutes} min` : null,
    r.difficulty ? labelize(r.difficulty) : null,
  ].filter(Boolean).map((m) => `<span>${m}</span>`).join("<i>·</i>");
  return `
    <article class="res">
      <div class="res__top">
        <span class="res__kind">${KIND_ICON[r.kind] || "🔗"} ${esc(labelize(r.kind || "link"))}</span>
        ${r.relevance != null ? `<span class="res__rel" title="relevance">★ ${r.relevance}</span>` : ""}
      </div>
      <h4><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a></h4>
      ${r.summary ? `<p class="res__sum">${esc(r.summary)}</p>` : ""}
      <div class="res__meta">${meta}</div>
      ${tags}
      <div class="res__actions">
        <a class="btn btn-ghost btn-sm" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Open ↗</a>
        <button class="btn btn-sm ${saved ? "btn-ghost" : "btn-primary"}" data-act="${saved ? "unsave" : "save"}" data-pid="${esc(r.public_id)}">
          ${saved ? "✓ Saved" : "Save"}
        </button>
      </div>
    </article>`;
}

function studyToolbar(topics) {
  const chips = (topics && topics.length)
    ? topics.slice(0, 6).map((t) => `<span class="mini-chip">${esc(t)}</span>`).join("")
    : `<span class="mini-chip mini-chip--muted">no topics yet</span>`;
  return `
    <div class="study-bar">
      <div class="subtabs" id="subtabs">
        <button data-tab="feed" class="${studyTab === "feed" ? "on" : ""}">Discover</button>
        <button data-tab="library" class="${studyTab === "library" ? "on" : ""}">My library</button>
      </div>
      <div class="study-bar__right">
        <span class="study-topics">${chips}</span>
        <button class="btn btn-primary btn-sm" id="genBtn">✦ Generate</button>
      </div>
    </div>`;
}

async function renderStudy() {
  const topics = state.preferences?.topics || [];
  app.innerHTML = appShell(
    "study",
    `<a class="back" href="#/dashboard">← Dashboard</a>
      <div class="section-head">
        <h2>Study material</h2>
        <p>AI-curated resources for your topics. Save the best to build your library.</p>
      </div>
      ${studyToolbar(topics)}
      <div id="studyBody"><div class="empty">Loading…</div></div>`
  );
  wireShell();

  $("#subtabs").querySelectorAll("button").forEach((b) => {
    b.onclick = () => { studyTab = b.dataset.tab; renderStudy(); };
  });

  $("#genBtn").onclick = (e) =>
    withLoading(e.currentTarget, "Generating…", async () => {
      try {
        const res = await api("/study-material/generate", { method: "POST", auth: true, body: {} });
        toast(res.generated ? `Curated ${res.generated} resources` : "No new resources found", "ok");
        studyTab = "feed";
        await loadStudyBody();
      } catch (err) {
        toast(err.message, "err");
      }
    });

  await loadStudyBody();
}

async function loadStudyBody() {
  const body = $("#studyBody");
  if (!body) return;
  body.innerHTML = `<div class="empty">Loading…</div>`;
  try {
    if (studyTab === "library") return await renderLibrary(body);
    return await renderFeed(body);
  } catch (err) {
    body.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
}

async function renderFeed(body) {
  const feed = await api("/study-material", { auth: true });
  if (!feed.length) {
    body.innerHTML = `<div class="emptybox">
      <div class="emptybox__emoji">📚</div>
      <h3>No study material yet</h3>
      <p>Hit <b>Generate</b> and we'll search the web and curate the best resources for your topics.</p>
    </div>`;
    return;
  }
  body.innerHTML = `<div class="res-grid">${feed.map((r) => resourceCard(r, { saved: r.is_saved })).join("")}</div>`;
  wireResourceActions(body);
}

async function renderLibrary(body) {
  const saved = await api("/study-material/library", { auth: true });
  const list = saved.map((s) => s.resource);
  const header = `
    <form id="libSearch" class="lib-search">
      <input name="q" placeholder="Search your library…" />
      <button class="btn btn-ghost btn-sm" type="submit">Search</button>
    </form>`;
  if (!list.length) {
    body.innerHTML = header + `<div class="emptybox">
      <div class="emptybox__emoji">🔖</div>
      <h3>Your library is empty</h3>
      <p>Save resources from <b>Discover</b> and they'll collect here.</p>
    </div>`;
    wireLibSearch(body);
    return;
  }
  body.innerHTML = header + `<div class="res-grid" id="libGrid">${list.map((r) => resourceCard(r, { saved: true })).join("")}</div>`;
  wireResourceActions(body);
  wireLibSearch(body);
}

function wireLibSearch(body) {
  const form = body.querySelector("#libSearch");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = form.q.value.trim();
    if (q.length < 2) return;
    withLoading(form.querySelector("button"), "Searching…", async () => {
      try {
        const hits = await api(`/study-material/library/search?q=${encodeURIComponent(q)}`, { auth: true });
        const grid = body.querySelector("#libGrid") || (() => {
          const d = document.createElement("div");
          d.id = "libGrid";
          d.className = "res-grid";
          body.appendChild(d);
          return d;
        })();
        if (!hits.length) {
          grid.innerHTML = `<p class="empty">No matches in your library.</p>`;
          return;
        }
        grid.innerHTML = hits
          .map((h) => resourceCard({ ...h.resource, relevance: Math.round(h.score * 100) }, { saved: true }))
          .join("");
        wireResourceActions(body);
      } catch (err) {
        toast(err.message, "err");
      }
    });
  });
}

function wireResourceActions(root) {
  root.querySelectorAll("button[data-act]").forEach((btn) => {
    btn.onclick = async () => {
      const pid = btn.dataset.pid;
      const act = btn.dataset.act;
      btn.disabled = true;
      try {
        if (act === "save") {
          await api(`/study-material/${pid}/save`, { method: "POST", auth: true, body: {} });
          toast("Saved to library", "ok");
        } else {
          await api(`/study-material/${pid}/save`, { method: "DELETE", auth: true });
          toast("Removed from library", "");
        }
        await loadStudyBody();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
}

// ── quizzes / tests ───────────────────────────────────────────────────────────
// Remembered across renders so the generate control keeps the user's choice.
let quizNum = 5;
// Holds the in-progress attempt (selected answers + start time) while taking.
let takeState = null;
let quizTimer;

async function renderQuizzes() {
  app.innerHTML = appShell(
    "quizzes",
    `<a class="back" href="#/dashboard">← Dashboard</a>
      <div class="section-head">
        <h2>Quizzes &amp; tests</h2>
        <p>AI-generated MCQs from your topics. Take a quiz for instant scoring, explanations, and progress.</p>
      </div>
      <div class="quiz-gen">
        <div class="quiz-gen__field">
          <label>Questions</label>
          <div class="segmented" id="numSeg">
            ${[3, 5, 10].map((n) => `<button data-n="${n}" class="${quizNum === n ? "on" : ""}">${n}</button>`).join("")}
          </div>
        </div>
        <button class="btn btn-primary" id="genQuiz">✦ Generate quiz</button>
      </div>
      <div id="statsBox"></div>
      <div id="quizList"><div class="empty">Loading…</div></div>`
  );
  wireShell();

  $("#numSeg").querySelectorAll("button").forEach((b) => {
    b.onclick = () => {
      quizNum = +b.dataset.n;
      $("#numSeg").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    };
  });

  $("#genQuiz").onclick = (e) =>
    withLoading(e.currentTarget, "Generating…", async () => {
      try {
        const quiz = await api("/assessments/quizzes/generate", {
          method: "POST",
          auth: true,
          body: { num_questions: quizNum },
        });
        toast(`Created a ${quiz.num_questions}-question quiz`, "ok");
        go(`#/quiz/${quiz.public_id}`);
      } catch (err) {
        toast(err.message, "err");
      }
    });

  await Promise.all([loadQuizStats(), loadQuizList()]);
}

async function loadQuizStats() {
  const box = $("#statsBox");
  if (!box) return;
  try {
    const s = await api("/assessments/stats", { auth: true });
    box.innerHTML = statsView(s);
  } catch {
    box.innerHTML = ""; // stats are a nice-to-have; never block the page
  }
}

function statsView(s) {
  if (!s || !s.answered) return "";
  const tone = s.accuracy >= 70 ? "badge--ok" : "badge--warn";
  return `<div class="panel stats">
      <div class="panel__head">
        <h3>Your progress</h3>
        <span class="badge ${tone}">${Math.round(s.accuracy)}% overall · ${s.correct}/${s.answered}</span>
      </div>
      <div class="stat-bars">
        ${s.per_topic
          .map(
            (t) => `<div class="stat-row">
              <div class="stat-row__top"><span>${esc(t.topic)}</span><span>${t.correct}/${t.answered}</span></div>
              <div class="bar"><div class="bar__fill ${scoreTone(t.accuracy)}" style="width:${Math.max(4, Math.round(t.accuracy))}%"></div></div>
            </div>`
          )
          .join("")}
      </div>
    </div>`;
}

async function loadQuizList() {
  const list = $("#quizList");
  if (!list) return;
  try {
    const quizzes = await api("/assessments/quizzes", { auth: true });
    if (!quizzes.length) {
      list.innerHTML = `<div class="emptybox">
        <div class="emptybox__emoji">📝</div>
        <h3>No quizzes yet</h3>
        <p>Pick how many questions and hit <b>Generate quiz</b> — we'll build one from your topics.</p>
      </div>`;
      return;
    }
    list.innerHTML = `<div class="quiz-list">${quizzes.map(quizCard).join("")}</div>`;
    list.querySelectorAll("button[data-take]").forEach((b) => {
      b.onclick = () => go(`#/quiz/${b.dataset.take}`);
    });
    list.querySelectorAll("button[data-review]").forEach((b) => {
      b.onclick = () => go(`#/quiz/${b.dataset.review}/result`);
    });
  } catch (err) {
    list.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
}

function quizCard(q) {
  const taken = q.attempt_count > 0;
  const pct = taken && q.num_questions ? Math.round((100 * q.best_score) / q.num_questions) : null;
  const attempts = `${q.attempt_count} attempt${q.attempt_count > 1 ? "s" : ""}`;
  return `<article class="quiz-card">
      <div class="quiz-card__main">
        <h4>${esc(q.title)}</h4>
        <div class="quiz-card__meta">
          <span>${q.num_questions} questions</span><i>·</i>
          <span>${labelize(q.difficulty)}</span>
          ${taken ? `<i>·</i><span>${attempts}</span>` : ""}
        </div>
        ${q.topics && q.topics.length ? `<div class="taglist">${q.topics.slice(0, 5).map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
      </div>
      <div class="quiz-card__side">
        ${taken ? `<div class="score-pill ${scoreTone(pct)}" title="best score">${pct}%</div>` : `<span class="badge">New</span>`}
        <div class="quiz-card__actions">
          <button class="btn btn-primary btn-sm" data-take="${esc(q.public_id)}">${taken ? "Retake" : "Take"}</button>
          ${taken ? `<button class="btn btn-ghost btn-sm" data-review="${esc(q.public_id)}">Review</button>` : ""}
        </div>
      </div>
    </article>`;
}

function scoreTone(pct) {
  return pct >= 70 ? "good" : pct >= 40 ? "mid" : "low";
}

// ── taking a quiz (timed) ─────────────────────────────────────────────────────
async function renderQuiz(pid) {
  app.innerHTML = appShell("quizzes", `<div class="empty">Loading quiz…</div>`);
  wireShell();
  let quiz;
  try {
    quiz = await api(`/assessments/quizzes/${pid}`, { auth: true });
  } catch (err) {
    app.innerHTML = appShell(
      "quizzes",
      `<a class="back" href="#/quizzes">← Quizzes</a><p class="empty">${esc(err.message)}</p>`
    );
    wireShell();
    return;
  }
  takeState = { pid, answers: {}, startedAt: Date.now() };

  app.innerHTML = appShell(
    "quizzes",
    `<a class="back" href="#/quizzes">← Quizzes</a>
      <div class="quiz-head">
        <div>
          <h2>${esc(quiz.title)}</h2>
          <p>${quiz.num_questions} questions · ${labelize(quiz.difficulty)}</p>
        </div>
        <div class="quiz-timer" id="timer">00:00</div>
      </div>
      <form id="quizForm">
        ${quiz.questions.map((q, i) => questionField(q, i)).join("")}
        <div class="quiz-submitbar">
          <span class="quiz-progress" id="quizProgress">0 of ${quiz.questions.length} answered</span>
          <button class="btn btn-primary" type="submit" id="submitQuiz">Submit answers</button>
        </div>
      </form>`
  );
  wireShell();
  startTimer();

  const form = $("#quizForm");
  const total = quiz.questions.length;
  const updateProgress = () => {
    const answered = form.querySelectorAll("input[type=radio]:checked").length;
    $("#quizProgress").textContent = `${answered} of ${total} answered`;
  };
  form.addEventListener("change", updateProgress);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const answers = quiz.questions.map((q) => {
      const checked = form.querySelector(`input[name="q_${q.public_id}"]:checked`);
      return { question_id: q.public_id, selected_index: checked ? +checked.value : null };
    });
    const blank = answers.filter((a) => a.selected_index === null).length;
    if (blank && !confirm(`${blank} question${blank > 1 ? "s are" : " is"} unanswered. Submit anyway?`)) {
      return;
    }
    withLoading($("#submitQuiz"), "Scoring…", async () => {
      try {
        await api(`/assessments/quizzes/${pid}/submit`, { method: "POST", auth: true, body: { answers } });
        clearInterval(quizTimer);
        go(`#/quiz/${pid}/result`);
      } catch (err) {
        toast(err.message, "err");
      }
    });
  });
}

function questionField(q, i) {
  return `<div class="qcard">
      <div class="qcard__stem"><span class="qnum">${i + 1}</span><span>${esc(q.stem)}</span></div>
      <div class="qopts">
        ${q.options
          .map(
            (o, oi) => `<label class="qopt">
              <input type="radio" name="q_${esc(q.public_id)}" value="${oi}">
              <span class="qopt__mark">${String.fromCharCode(65 + oi)}</span>
              <span class="qopt__txt">${esc(o)}</span>
            </label>`
          )
          .join("")}
      </div>
    </div>`;
}

function startTimer() {
  clearInterval(quizTimer);
  const start = takeState.startedAt;
  quizTimer = setInterval(() => {
    const el = document.getElementById("timer");
    if (!el) return clearInterval(quizTimer); // navigated away
    const s = Math.floor((Date.now() - start) / 1000);
    el.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);
}

// ── reviewing a graded attempt ────────────────────────────────────────────────
async function renderQuizResult(pid) {
  app.innerHTML = appShell("quizzes", `<div class="empty">Loading result…</div>`);
  wireShell();
  let res;
  try {
    res = await api(`/assessments/quizzes/${pid}/result`, { auth: true });
  } catch (err) {
    app.innerHTML = appShell(
      "quizzes",
      `<a class="back" href="#/quizzes">← Quizzes</a><p class="empty">${esc(err.message)}</p>`
    );
    wireShell();
    return;
  }
  app.innerHTML = appShell("quizzes", resultView(res));
  wireShell();
  const retake = $("#retake");
  if (retake) retake.onclick = () => go(`#/quiz/${pid}`);
}

function resultView(res) {
  const pct = res.percentage;
  const tone = scoreTone(pct);
  const heading = pct >= 70 ? "Great work! 🎉" : pct >= 40 ? "Good effort 👍" : "Keep practicing 💪";
  return `<a class="back" href="#/quizzes">← Quizzes</a>
      <div class="result-head">
        <div class="result-score ${tone}">
          <span class="result-score__pct">${Math.round(pct)}%</span>
          <span class="result-score__frac">${res.score}/${res.total}</span>
        </div>
        <div class="result-head__body">
          <h2>${heading}</h2>
          <p>You answered ${res.score} of ${res.total} correctly.</p>
          <div class="actions" style="justify-content:flex-start;margin-top:14px">
            <button class="btn btn-primary btn-sm" id="retake">Retake quiz</button>
            <a class="btn btn-ghost btn-sm" href="#/quizzes">All quizzes</a>
          </div>
        </div>
      </div>
      <div class="answers">${res.answers.map(answerCard).join("")}</div>`;
}

function answerCard(a, i) {
  return `<div class="qcard qcard--${a.is_correct ? "correct" : "wrong"}">
      <div class="qcard__stem"><span class="qnum">${i + 1}</span><span>${esc(a.stem)}</span></div>
      <div class="qopts qopts--review">
        ${a.options
          .map((o, oi) => {
            const isCorrect = oi === a.correct_index;
            const isPicked = oi === a.selected_index;
            const cls = isCorrect ? "qopt qopt--correct" : isPicked ? "qopt qopt--wrong" : "qopt";
            const mark = isCorrect ? "✓" : isPicked ? "✗" : String.fromCharCode(65 + oi);
            return `<div class="${cls}"><span class="qopt__mark">${mark}</span><span class="qopt__txt">${esc(o)}</span></div>`;
          })
          .join("")}
      </div>
      ${a.selected_index == null ? `<p class="qexpl qexpl--skip">⤳ You skipped this question.</p>` : ""}
      ${a.explanation ? `<p class="qexpl">💡 ${esc(a.explanation)}</p>` : ""}
    </div>`;
}

// ── mock tests (formal, sectional, timed) ──────────────────────────────────────
let mockCfg = { difficulty: "intermediate", sections: 3, perSection: 5 };
let mockTimer;

function numSegWire(sel, onPick) {
  const g = $(sel);
  g.querySelectorAll("button").forEach((b) => {
    b.onclick = () => {
      g.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      onPick(+b.dataset.n);
    };
  });
}

function fmtSecs(s) {
  if (s == null) return "—";
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

async function renderMockTests() {
  app.innerHTML = appShell(
    "mock",
    `<a class="back" href="#/dashboard">← Dashboard</a>
      <div class="section-head">
        <h2>Mock tests</h2>
        <p>Full-length, sectional, timed exams — with a detailed report: section scores, percentile, time analysis and your weak areas. One submission each.</p>
      </div>
      <div class="panel mock-gen">
        <div class="mock-gen__grid">
          <div class="quiz-gen__field">
            <label>Difficulty</label>
            <div class="segmented" id="mDiff">${seg(["beginner", "intermediate", "advanced"], mockCfg.difficulty)}</div>
          </div>
          <div class="quiz-gen__field">
            <label>Sections</label>
            <div class="segmented" id="mSecs">${[2, 3, 4].map((n) => `<button data-n="${n}" class="${mockCfg.sections === n ? "on" : ""}">${n}</button>`).join("")}</div>
          </div>
          <div class="quiz-gen__field">
            <label>Questions / section</label>
            <div class="segmented" id="mPer">${[3, 5, 10].map((n) => `<button data-n="${n}" class="${mockCfg.perSection === n ? "on" : ""}">${n}</button>`).join("")}</div>
          </div>
        </div>
        <div class="mock-gen__foot">
          <span class="hint" id="mockHint"></span>
          <button class="btn btn-primary" id="genMock">✦ Generate mock test</button>
        </div>
      </div>
      <div id="mockList"><div class="empty">Loading…</div></div>`
  );
  wireShell();

  const updateHint = () => {
    const total = mockCfg.sections * mockCfg.perSection;
    $("#mockHint").textContent = `≈ ${total} questions · ~${total} min · built from your topics`;
  };
  segWire("#mDiff", (v) => (mockCfg.difficulty = v));
  numSegWire("#mSecs", (n) => { mockCfg.sections = n; updateHint(); });
  numSegWire("#mPer", (n) => { mockCfg.perSection = n; updateHint(); });
  updateHint();

  $("#genMock").onclick = (e) =>
    withLoading(e.currentTarget, "Generating… this can take a moment", async () => {
      try {
        const t = await api("/assessments/mock-tests/generate", {
          method: "POST",
          auth: true,
          body: {
            difficulty: mockCfg.difficulty,
            num_sections: mockCfg.sections,
            questions_per_section: mockCfg.perSection,
          },
        });
        toast(`Created a ${t.total_questions}-question mock test`, "ok");
        go(`#/mock/${t.public_id}`);
      } catch (err) {
        toast(err.message, "err");
      }
    });

  await loadMockList();
}

async function loadMockList() {
  const list = $("#mockList");
  if (!list) return;
  try {
    const tests = await api("/assessments/mock-tests", { auth: true });
    if (!tests.length) {
      list.innerHTML = `<div class="emptybox">
        <div class="emptybox__emoji">📋</div>
        <h3>No mock tests yet</h3>
        <p>Choose difficulty &amp; size, then hit <b>Generate mock test</b> — we'll build a sectional, timed exam from your topics.</p>
      </div>`;
      return;
    }
    list.innerHTML = `<div class="quiz-list">${tests.map(mockCard).join("")}</div>`;
    list.querySelectorAll("button[data-take]").forEach((b) => {
      b.onclick = () => go(`#/mock/${b.dataset.take}`);
    });
    list.querySelectorAll("button[data-report]").forEach((b) => {
      b.onclick = () => go(`#/mock/${b.dataset.report}/report`);
    });
  } catch (err) {
    list.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
}

function mockCard(m) {
  const submitted = m.status === "submitted";
  const mins = Math.round(m.duration_seconds / 60);
  const statusLabel = { created: "New", in_progress: "In progress", submitted: "Submitted" }[m.status];
  const action = submitted
    ? `<button class="btn btn-ghost btn-sm" data-report="${esc(m.public_id)}">View report</button>`
    : `<button class="btn btn-primary btn-sm" data-take="${esc(m.public_id)}">${m.status === "in_progress" ? "Resume" : "Start"}</button>`;
  return `<article class="quiz-card">
      <div class="quiz-card__main">
        <h4>${esc(m.title)}</h4>
        <div class="quiz-card__meta">
          <span>${m.total_questions} questions</span><i>·</i>
          <span>${labelize(m.difficulty)}</span><i>·</i>
          <span>${mins} min</span>
        </div>
      </div>
      <div class="quiz-card__side">
        ${submitted && m.percentage != null
          ? `<div class="score-pill ${scoreTone(m.percentage)}" title="score">${Math.round(m.percentage)}%</div>`
          : `<span class="badge ${m.status === "in_progress" ? "badge--warn" : ""}">${statusLabel}</span>`}
        <div class="quiz-card__actions">${action}</div>
      </div>
    </article>`;
}

// ── taking a mock test (sectional, timed countdown) ─────────────────────────────
async function renderMockTake(pid) {
  app.innerHTML = appShell("mock", `<div class="empty">Loading mock test…</div>`);
  wireShell();
  let t;
  try {
    t = await api(`/assessments/mock-tests/${pid}`, { auth: true });
  } catch (err) {
    app.innerHTML = appShell(
      "mock",
      `<a class="back" href="#/mock-tests">← Mock tests</a><p class="empty">${esc(err.message)}</p>`
    );
    wireShell();
    return;
  }
  if (t.submitted_at) return go(`#/mock/${pid}/report`); // already done → straight to report

  const startedMs = Date.parse(t.started_at) || Date.now();

  app.innerHTML = appShell(
    "mock",
    `<a class="back" href="#/mock-tests">← Mock tests</a>
      <div class="quiz-head">
        <div>
          <h2>${esc(t.title)}</h2>
          <p>${t.total_questions} questions · ${t.sections.length} section${t.sections.length > 1 ? "s" : ""} · ${labelize(t.difficulty)}</p>
        </div>
        <div class="quiz-timer" id="mtimer" title="time remaining">--:--</div>
      </div>
      <form id="mockForm">
        ${mockSectionsHtml(t.sections)}
        <div class="quiz-submitbar">
          <span class="quiz-progress" id="mockProgress">0 of ${t.total_questions} answered</span>
          <button class="btn btn-primary" type="submit" id="submitMock">Submit mock test</button>
        </div>
      </form>`
  );
  wireShell();

  const form = $("#mockForm");
  const update = () => {
    const answered = form.querySelectorAll("input[type=radio]:checked").length;
    $("#mockProgress").textContent = `${answered} of ${t.total_questions} answered`;
  };
  form.addEventListener("change", update);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    submitMock(pid, t, false);
  });

  startMockCountdown(startedMs, t.duration_seconds, () => submitMock(pid, t, true));
}

function mockSectionsHtml(sections) {
  let n = 0; // continuous question numbering across sections
  return sections
    .map((s) => {
      const mins = s.duration_seconds ? ` · ${Math.round(s.duration_seconds / 60)} min` : "";
      const tags = s.topics && s.topics.length
        ? `<div class="taglist">${s.topics.slice(0, 6).map((x) => `<span>${esc(x)}</span>`).join("")}</div>`
        : "";
      const head = `<div class="mock-section">
          <div class="mock-section__title">${esc(s.title)}</div>
          <div class="mock-section__meta">${s.questions.length} questions${mins}</div>
          ${tags}
        </div>`;
      const qs = s.questions.map((q) => questionField(q, n++)).join("");
      return head + qs;
    })
    .join("");
}

function collectMockAnswers(t) {
  const form = $("#mockForm");
  const out = [];
  t.sections.forEach((s) =>
    s.questions.forEach((q) => {
      const checked = form.querySelector(`input[name="q_${q.public_id}"]:checked`);
      out.push({ question_id: q.public_id, selected_index: checked ? +checked.value : null });
    })
  );
  return out;
}

function submitMock(pid, t, auto) {
  const answers = collectMockAnswers(t);
  if (!auto) {
    const blank = answers.filter((a) => a.selected_index === null).length;
    if (blank && !confirm(`${blank} question${blank > 1 ? "s are" : " is"} unanswered. Submit the mock test? You can't retake it.`)) {
      return;
    }
  }
  const btn = $("#submitMock");
  withLoading(btn, auto ? "Time's up — scoring…" : "Scoring…", async () => {
    try {
      clearInterval(mockTimer);
      await api(`/assessments/mock-tests/${pid}/submit`, { method: "POST", auth: true, body: { answers } });
      go(`#/mock/${pid}/report`);
    } catch (err) {
      toast(err.message, "err");
    }
  });
}

function startMockCountdown(startedMs, durationSec, onExpire) {
  clearInterval(mockTimer);
  const el = $("#mtimer");
  if (!durationSec) {
    if (el) el.textContent = "∞";
    return; // untimed
  }
  const tick = () => {
    const node = document.getElementById("mtimer");
    if (!node) return clearInterval(mockTimer); // navigated away
    let rem = durationSec - Math.floor((Date.now() - startedMs) / 1000);
    if (rem <= 0) {
      node.textContent = "00:00";
      node.classList.add("danger");
      clearInterval(mockTimer);
      onExpire();
      return;
    }
    node.textContent = fmtSecs(rem);
    node.classList.toggle("danger", rem <= 60);
  };
  tick();
  mockTimer = setInterval(tick, 1000);
}

// ── mock-test report ────────────────────────────────────────────────────────────
async function renderMockReport(pid) {
  app.innerHTML = appShell("mock", `<div class="empty">Loading report…</div>`);
  wireShell();
  let r;
  try {
    r = await api(`/assessments/mock-tests/${pid}/report`, { auth: true });
  } catch (err) {
    app.innerHTML = appShell(
      "mock",
      `<a class="back" href="#/mock-tests">← Mock tests</a><p class="empty">${esc(err.message)}</p>`
    );
    wireShell();
    return;
  }
  app.innerHTML = appShell("mock", mockReportView(r));
  wireShell();
  app.querySelectorAll("button[data-quiztopic]").forEach((b) => {
    b.onclick = () =>
      withLoading(b, "Building…", async () => {
        try {
          const q = await api("/assessments/quizzes/generate", {
            method: "POST",
            auth: true,
            body: { topics: [b.dataset.quiztopic], num_questions: 5 },
          });
          go(`#/quiz/${q.public_id}`);
        } catch (err) {
          toast(err.message, "err");
        }
      });
  });
}

function mockReportView(r) {
  const pct = r.percentage;
  const tone = scoreTone(pct);
  const heading = pct >= 70 ? "Strong result! 🎉" : pct >= 40 ? "Solid attempt 👍" : "Room to grow 💪";
  const pctile =
    r.percentile != null
      ? `<span class="badge badge--ok" title="vs others at this difficulty">Top ${Math.max(1, Math.round(100 - r.percentile))}% · ${Math.round(r.percentile)}th pctile</span>`
      : "";

  const sections = r.sections
    .map(
      (s) => `<div class="stat-row">
        <div class="stat-row__top">
          <span>${esc(s.title)}</span>
          <span>${s.correct}/${s.total}${s.avg_seconds_per_question != null ? ` · ${s.avg_seconds_per_question}s/q` : ""}</span>
        </div>
        <div class="bar"><div class="bar__fill ${scoreTone(s.accuracy)}" style="width:${Math.max(4, Math.round(s.accuracy))}%"></div></div>
      </div>`
    )
    .join("");

  const weak = r.weak_areas.length
    ? `<div class="panel">
        <div class="panel__head"><h3>Weak areas to focus on</h3></div>
        <div class="weak-list">
          ${r.weak_areas
            .map(
              (w) => `<div class="weak-row">
                <div class="weak-row__info">
                  <span class="weak-row__topic">${esc(w.topic)}</span>
                  <span class="weak-row__acc ${scoreTone(w.accuracy)}">${Math.round(w.accuracy)}% · ${w.correct}/${w.answered}</span>
                </div>
                <button class="btn btn-ghost btn-sm" data-quiztopic="${esc(w.topic)}">Quiz me on this →</button>
              </div>`
            )
            .join("")}
        </div>
      </div>`
    : `<div class="panel"><p class="empty" style="font-style:normal">✅ No weak areas — you cleared every topic above ${60}%. Nice.</p></div>`;

  return `<a class="back" href="#/mock-tests">← Mock tests</a>
      <div class="result-head">
        <div class="result-score ${tone}">
          <span class="result-score__pct">${Math.round(pct)}%</span>
          <span class="result-score__frac">${r.score}/${r.total}</span>
        </div>
        <div class="result-head__body">
          <h2>${heading}</h2>
          <p>${esc(r.title)} · ${labelize(r.difficulty)}</p>
          <div class="mock-report__pills">
            ${pctile}
            <span class="badge">⏱ ${fmtSecs(r.time.time_taken_seconds)} / ${fmtSecs(r.time.duration_seconds)}</span>
            ${r.time.avg_seconds_per_question != null ? `<span class="badge">~${r.time.avg_seconds_per_question}s per question</span>` : ""}
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel__head"><h3>Section scores</h3></div>
        <div class="stat-bars">${sections}</div>
      </div>

      ${weak}

      <h3 class="mock-report__answers-h">Review answers</h3>
      <div class="answers">${r.answers.map(answerCard).join("")}</div>`;
}

// ── courses ───────────────────────────────────────────────────────────────────
let coursesTab = "discover"; // "discover" | "recommended" | "mine"

async function renderCourses() {
  app.innerHTML = appShell(
    "courses",
    `<a class="back" href="#/dashboard">← Dashboard</a>
      <div class="section-head">
        <h2>Courses &amp; certifications</h2>
        <p>Structured learning paths. Enrol, work through the lessons, and earn a certificate.</p>
      </div>
      <div class="study-bar">
        <div class="subtabs" id="csubtabs">
          <button data-tab="discover" class="${coursesTab === "discover" ? "on" : ""}">Discover</button>
          <button data-tab="recommended" class="${coursesTab === "recommended" ? "on" : ""}">For you</button>
          <button data-tab="mine" class="${coursesTab === "mine" ? "on" : ""}">My courses</button>
        </div>
      </div>
      <div id="coursesBody"><div class="empty">Loading…</div></div>`
  );
  wireShell();
  $("#csubtabs").querySelectorAll("button").forEach((b) => {
    b.onclick = () => { coursesTab = b.dataset.tab; renderCourses(); };
  });
  await loadCoursesBody();
}

async function loadCoursesBody() {
  const body = $("#coursesBody");
  if (!body) return;
  body.innerHTML = `<div class="empty">Loading…</div>`;
  try {
    if (coursesTab === "mine") {
      const enrolled = await api("/courses/me", { auth: true });
      if (!enrolled.length) {
        body.innerHTML = emptyBox("🎓", "No courses yet", "Enrol from <b>Discover</b> and they'll show up here with your progress.");
        return;
      }
      body.innerHTML = `<div class="course-grid">${enrolled.map((e) => courseCard(e.course, e)).join("")}</div>`;
    } else {
      const path = coursesTab === "recommended" ? "/courses/recommended" : "/courses";
      const list = await api(path, { auth: true });
      if (!list.length) {
        body.innerHTML = emptyBox("🎓", "No courses to show", coursesTab === "recommended"
          ? "Set a few topics in your preferences and we'll match courses to you."
          : "The catalog is empty right now — check back soon.");
        return;
      }
      body.innerHTML = `<div class="course-grid">${list.map((c) => courseCard(c)).join("")}</div>`;
    }
    body.querySelectorAll("[data-course]").forEach((el) => {
      el.onclick = () => go(`#/course/${el.dataset.course}`);
    });
  } catch (err) {
    body.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
}

function emptyBox(emoji, title, html) {
  return `<div class="emptybox"><div class="emptybox__emoji">${emoji}</div><h3>${esc(title)}</h3><p>${html}</p></div>`;
}

// `c` is a CourseSummary; `enr` (optional) carries progress/cert when enrolled.
function courseCard(c, enr) {
  const meta = [labelize(c.level), c.category, `${c.lesson_count} lesson${c.lesson_count === 1 ? "" : "s"}`]
    .filter(Boolean).map((m) => `<span>${esc(m)}</span>`).join("<i>·</i>");
  const tags = (c.tags && c.tags.length)
    ? `<div class="taglist">${c.tags.slice(0, 4).map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : "";
  const enrolled = c.is_enrolled || (enr && enr.status);
  const progress = (enr && enr.progress != null) ? enr.progress : c.progress || 0;
  const done = enrolled && (enr?.status === "completed" || c.status === "completed");
  let footer;
  if (done) footer = `<span class="badge badge--ok">✓ Completed</span>`;
  else if (enrolled) footer = `<div class="course-prog"><div class="bar"><div class="bar__fill ${scoreTone(progress)}" style="width:${Math.max(4, progress)}%"></div></div><span>${progress}%</span></div>`;
  else footer = `<span class="badge">Not enrolled</span>`;
  return `<article class="course-card" data-course="${esc(c.public_id)}" role="button" tabindex="0">
      <div class="course-card__emoji">${esc(c.emoji || "📘")}</div>
      <div class="course-card__body">
        <h4>${esc(c.title)}</h4>
        ${c.subtitle ? `<p class="course-card__sub">${esc(c.subtitle)}</p>` : ""}
        <div class="course-card__meta">${meta}</div>
        ${tags}
      </div>
      <div class="course-card__foot">${footer}</div>
    </article>`;
}

async function renderCourseDetail(pid) {
  app.innerHTML = appShell("courses", `<div class="empty">Loading course…</div>`);
  wireShell();
  let c;
  try {
    c = await api(`/courses/${pid}`, { auth: true });
  } catch (err) {
    app.innerHTML = appShell("courses", `<a class="back" href="#/courses">← Courses</a><p class="empty">${esc(err.message)}</p>`);
    wireShell();
    return;
  }

  const total = c.modules.reduce((n, m) => n + m.lessons.length, 0);
  const cert = await fetchCourseCertificate(pid, c);

  app.innerHTML = appShell("courses", courseDetailView(c, total, cert));
  wireShell();
  wireCourseDetail(c, pid);
}

// The detail endpoint doesn't embed the certificate; pull it from /courses/me when completed.
async function fetchCourseCertificate(pid, c) {
  if (c.status !== "completed") return null;
  try {
    const mine = await api("/courses/me", { auth: true });
    const row = mine.find((e) => e.course.public_id === pid);
    return row ? row.certificate : null;
  } catch { return null; }
}

function courseDetailView(c, total, cert) {
  const meta = [labelize(c.level), c.category, c.est_minutes ? `${c.est_minutes} min` : null, `${total} lessons`]
    .filter(Boolean).map((m) => `<span>${esc(m)}</span>`).join("<i>·</i>");
  const enrolled = c.is_enrolled;
  const progress = c.progress || 0;
  const completed = c.status === "completed";

  let cta;
  if (!enrolled) cta = `<button class="btn btn-primary" id="enrollBtn">Enrol in this course</button>`;
  else cta = `<div class="course-detail__prog">
      <div class="bar"><div class="bar__fill ${scoreTone(progress)}" style="width:${Math.max(4, progress)}%"></div></div>
      <span>${progress}% complete${completed ? " · ✓ done" : ""}</span>
    </div>`;

  const certCard = (completed && cert)
    ? `<div class="panel cert-card">
        <div class="cert-card__icon">🏅</div>
        <div class="cert-card__body">
          <h3>Certificate earned</h3>
          <p>Certificate ID <b>${esc(cert.serial)}</b>${cert.revoked_at ? ' · <span class="badge badge--warn">revoked</span>' : ""}</p>
        </div>
        <a class="btn btn-primary btn-sm" href="${esc(API_BASE)}/certificates/verify/${esc(cert.public_id)}" target="_blank" rel="noopener noreferrer">View certificate ↗</a>
      </div>` : "";

  const modules = c.modules.map((m, mi) => `
    <div class="cmodule">
      <div class="cmodule__head"><span class="cmodule__num">${mi + 1}</span><div><h4>${esc(m.title)}</h4>${m.summary ? `<p>${esc(m.summary)}</p>` : ""}</div></div>
      <div class="clessons">
        ${m.lessons.map((l) => lessonRow(l, enrolled)).join("")}
      </div>
    </div>`).join("");

  return `<a class="back" href="#/courses">← Courses</a>
    <div class="course-hero">
      <div class="course-hero__emoji">${esc(c.emoji || "📘")}</div>
      <div class="course-hero__body">
        <h2>${esc(c.title)}</h2>
        ${c.subtitle ? `<p class="course-hero__sub">${esc(c.subtitle)}</p>` : ""}
        <div class="course-card__meta">${meta}</div>
      </div>
    </div>
    ${c.description ? `<p class="course-desc">${esc(c.description)}</p>` : ""}
    <div class="course-actions">
      ${cta}
      ${enrolled ? `<button class="btn btn-ghost" id="studyBtn">📚 Study this course</button>
      <button class="btn btn-ghost" id="quizBtn">📝 Quiz me on this</button>` : ""}
    </div>
    ${certCard}
    <div class="csyllabus">${modules}</div>`;
}

function lessonRow(l, enrolled) {
  const done = l.is_completed;
  const ctrl = enrolled
    ? `<button class="lesson__check ${done ? "on" : ""}" data-lesson="${esc(l.public_id)}" ${done ? "disabled" : ""} title="${done ? "Completed" : "Mark complete"}">${done ? "✓" : ""}</button>`
    : `<span class="lesson__check" aria-hidden="true"></span>`;
  return `<div class="lesson ${done ? "lesson--done" : ""}">
      ${ctrl}
      <div class="lesson__body">
        <span class="lesson__title">${esc(l.title)}</span>
        ${l.content ? `<span class="lesson__desc">${esc(l.content)}</span>` : ""}
      </div>
      ${l.est_minutes ? `<span class="lesson__min">${l.est_minutes}m</span>` : ""}
    </div>`;
}

function wireCourseDetail(c, pid) {
  const enrollBtn = $("#enrollBtn");
  if (enrollBtn) enrollBtn.onclick = (e) =>
    withLoading(e.currentTarget, "Enrolling…", async () => {
      try { await api(`/courses/${pid}/enroll`, { method: "POST", auth: true }); toast("Enrolled!", "ok"); renderCourseDetail(pid); }
      catch (err) { toast(err.message, "err"); }
    });

  const studyBtn = $("#studyBtn");
  if (studyBtn) studyBtn.onclick = (e) =>
    withLoading(e.currentTarget, "Curating…", async () => {
      try {
        const res = await api("/study-material/generate", { method: "POST", auth: true, body: { course_id: pid } });
        toast(res.generated ? `Curated ${res.generated} resources for this course` : "No new resources found", "ok");
        studyTab = "feed"; go("#/study");
      } catch (err) { toast(err.message, "err"); }
    });

  const quizBtn = $("#quizBtn");
  if (quizBtn) quizBtn.onclick = (e) =>
    withLoading(e.currentTarget, "Generating…", async () => {
      try {
        const quiz = await api("/assessments/quizzes/generate", { method: "POST", auth: true, body: { course_id: pid, num_questions: quizNum } });
        toast(`Created a ${quiz.num_questions}-question quiz`, "ok");
        go(`#/quiz/${quiz.public_id}`);
      } catch (err) { toast(err.message, "err"); }
    });

  app.querySelectorAll("button[data-lesson]").forEach((btn) => {
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        const enr = await api(`/courses/lessons/${btn.dataset.lesson}/complete`, { method: "POST", auth: true });
        if (enr.status === "completed") toast("🎉 Course complete — certificate issued!", "ok");
        renderCourseDetail(pid);
      } catch (err) { toast(err.message, "err"); btn.disabled = false; }
    };
  });
}

// ── admin: manage courses ──────────────────────────────────────────────────────
const COURSE_TEMPLATE = JSON.stringify({
  slug: "my-new-course",
  title: "My New Course",
  subtitle: "A short tagline",
  description: "What this course covers.",
  level: "beginner",
  category: "General",
  tags: ["topic-a", "topic-b"],
  emoji: "📘",
  is_published: true,
  modules: [
    { title: "Module 1", summary: "", lessons: [
      { title: "Lesson 1", content: "Lesson body.", topics: ["topic-a"], est_minutes: 30 },
    ] },
  ],
}, null, 2);

async function renderAdmin() {
  if (state.user?.role !== "admin") return go("#/dashboard");
  app.innerHTML = appShell(
    "admin",
    `<a class="back" href="#/dashboard">← Dashboard</a>
      <div class="section-head">
        <h2>Manage courses</h2>
        <p>Author the catalog. This same payload shape is what an org-data import will produce.</p>
      </div>
      <div class="panel">
        <div class="panel__head"><h3>New / replace course (JSON)</h3><button class="btn btn-ghost btn-sm" id="resetTpl">Reset template</button></div>
        <textarea id="courseJson" class="mono" rows="14">${esc(COURSE_TEMPLATE)}</textarea>
        <div class="error-text" id="adminErr"></div>
        <div class="actions" style="justify-content:flex-start"><button class="btn btn-primary" id="saveCourse">Save course</button></div>
      </div>
      <div id="adminList"><div class="empty">Loading…</div></div>`
  );
  wireShell();
  $("#resetTpl").onclick = () => { $("#courseJson").value = COURSE_TEMPLATE; };
  $("#saveCourse").onclick = (e) => {
    $("#adminErr").textContent = "";
    let payload;
    try { payload = JSON.parse($("#courseJson").value); }
    catch (err) { $("#adminErr").textContent = "Invalid JSON: " + err.message; return; }
    withLoading(e.currentTarget, "Saving…", async () => {
      try { await api("/admin/courses", { method: "POST", auth: true, body: payload }); toast("Course saved", "ok"); await loadAdminList(); }
      catch (err) { $("#adminErr").textContent = err.message; }
    });
  };
  await loadAdminList();
}

async function loadAdminList() {
  const box = $("#adminList");
  if (!box) return;
  try {
    const list = await api("/admin/courses", { auth: true });
    if (!list.length) { box.innerHTML = emptyBox("🛠️", "No courses yet", "Create one above."); return; }
    box.innerHTML = `<div class="panel"><div class="panel__head"><h3>Catalog (${list.length})</h3></div>
      <div class="admin-rows">${list.map(adminRow).join("")}</div></div>`;
    box.querySelectorAll("button[data-pub]").forEach((b) => {
      b.onclick = async () => {
        b.disabled = true;
        try { await api(`/admin/courses/${b.dataset.pub}/publish?published=${b.dataset.to}`, { method: "POST", auth: true }); toast("Updated", "ok"); await loadAdminList(); }
        catch (err) { toast(err.message, "err"); b.disabled = false; }
      };
    });
    box.querySelectorAll("button[data-del]").forEach((b) => {
      b.onclick = async () => {
        if (!confirm("Delete this course and all its enrollments? This cannot be undone.")) return;
        b.disabled = true;
        try { await api(`/admin/courses/${b.dataset.del}`, { method: "DELETE", auth: true }); toast("Deleted", ""); await loadAdminList(); }
        catch (err) { toast(err.message, "err"); b.disabled = false; }
      };
    });
  } catch (err) {
    box.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
}

function adminRow(c) {
  return `<div class="admin-row">
      <span class="admin-row__emoji">${esc(c.emoji || "📘")}</span>
      <div class="admin-row__main">
        <b>${esc(c.title)}</b>
        <span class="admin-row__meta">${esc(c.slug)} · ${c.module_count} mod · ${c.lesson_count} lessons · ${c.enrollment_count} enrolled · ${esc(c.source)}</span>
      </div>
      <span class="badge ${c.is_published ? "badge--ok" : "badge--warn"}">${c.is_published ? "Published" : "Draft"}</span>
      <div class="admin-row__actions">
        <button class="btn btn-ghost btn-sm" data-pub="${esc(c.public_id)}" data-to="${c.is_published ? "false" : "true"}">${c.is_published ? "Unpublish" : "Publish"}</button>
        <button class="btn btn-ghost btn-sm" data-del="${esc(c.public_id)}">Delete</button>
      </div>
    </div>`;
}

// ── state + routing ──────────────────────────────────────────────────────────
let state = {};

async function loadState() {
  const agg = await api("/users/me/profile", { auth: true });
  state = { user: agg.user, profile: agg.profile, preferences: agg.preferences };
  return state;
}

// After login/signup: send the user to the first unfinished step.
async function routeAfterAuth() {
  await loadState();
  if (!state.user.user_type) go("#/onboarding");
  else if (!state.preferences) go("#/preferences");
  else go("#/dashboard");
}

const PROTECTED = ["#/onboarding", "#/preferences", "#/dashboard", "#/study", "#/quizzes", "#/mock-tests", "#/courses", "#/admin"];

async function render() {
  const hash = location.hash || (getToken() ? "#/dashboard" : "#/signin");
  // #/quiz/<id>, #/quiz/<id>/result and #/course/<id> are dynamic (and protected) too.
  const isProtected =
    PROTECTED.includes(hash) ||
    hash.startsWith("#/quiz/") ||
    hash.startsWith("#/course/") ||
    hash.startsWith("#/mock/");

  if (!getToken() && isProtected) return go("#/signin");
  if (getToken() && (hash === "#/signin" || hash === "#/signup")) return go("#/dashboard");

  // Protected pages need fresh state; load it once if missing.
  if (isProtected && !state.user) {
    app.innerHTML = `<div class="center-screen">Loading…</div>`;
    try {
      await loadState();
    } catch (e) {
      toast(e.message, "err");
      return; // api() already redirected to signin on 401
    }
  }

  // Dynamic quiz routes: #/quiz/<pid> (take) and #/quiz/<pid>/result (review).
  if (hash.startsWith("#/quiz/")) {
    const seg = hash.split("/"); // ["#", "quiz", "<pid>", ("result")]
    const pid = seg[2];
    if (pid) return seg[3] === "result" ? renderQuizResult(pid) : renderQuiz(pid);
  }
  // Dynamic course route: #/course/<pid> (detail).
  if (hash.startsWith("#/course/")) {
    const pid = hash.split("/")[2];
    if (pid) return renderCourseDetail(pid);
  }
  // Dynamic mock-test routes: #/mock/<pid> (take) and #/mock/<pid>/report.
  if (hash.startsWith("#/mock/")) {
    const seg = hash.split("/"); // ["#", "mock", "<pid>", ("report")]
    const pid = seg[2];
    if (pid) return seg[3] === "report" ? renderMockReport(pid) : renderMockTake(pid);
  }

  switch (hash) {
    case "#/signup": return renderSignup();
    case "#/signin": return renderSignin();
    case "#/onboarding": return renderOnboarding();
    case "#/preferences": return renderPreferences();
    case "#/dashboard": return renderDashboard();
    case "#/study": return renderStudy();
    case "#/quizzes": return renderQuizzes();
    case "#/mock-tests": return renderMockTests();
    case "#/courses": return renderCourses();
    case "#/admin": return renderAdmin();
    default: return go(getToken() ? "#/dashboard" : "#/signin");
  }
}

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", render);
render();
