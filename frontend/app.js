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
            <div class="nav__label">Coming soon</div>
            <span class="nav__item nav__item--soon"><span class="nav__ic">🎓</span>Courses<em>Soon</em></span>
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

function studentFormHtml() {
  const p = state.profile && state.user?.user_type === "student" ? state.profile : {};
  return `
    <div class="panel">
      <form id="pform">
        <div class="row2">
          <div class="field">
            <label>Education level</label>
            <select name="education_level">
              ${["", "high_school", "undergraduate", "postgraduate", "other"]
                .map((v) => `<option value="${v}" ${p.education_level === v ? "selected" : ""}>${v ? labelize(v) : "Select…"}</option>`)
                .join("")}
            </select>
          </div>
          <div class="field">
            <label>Stream <span class="hint">(e.g. Science)</span></label>
            <input name="stream" value="${esc(p.stream || "")}" placeholder="Science / Commerce / Arts" />
          </div>
        </div>
        <div class="field"><label>Subjects</label><div id="subjects"></div></div>
        <div class="field"><label>Target exams <span class="hint">(e.g. JEE, NEET)</span></label><div id="exams"></div></div>
        <div class="field"><label>Preferred colleges</label><div id="colleges"></div></div>
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
  const subjects = chipsInput("Add a subject…", p.subjects || []);
  const exams = chipsInput("Add an exam…", p.target_exams || []);
  const colleges = chipsInput("Add a college…", p.preferred_colleges || []);
  $("#subjects").appendChild(subjects.el);
  $("#exams").appendChild(exams.el);
  $("#colleges").appendChild(colleges.el);

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
            user_type: "student",
            education_level: f.education_level.value || null,
            stream: f.stream.value.trim() || null,
            subjects: subjects.get(),
            target_exams: exams.get(),
            preferred_colleges: colleges.get(),
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
      </div>`
  );
  wireShell();
  $("#editProfile").onclick = () => go("#/onboarding");
  $("#editPrefs").onclick = () => go("#/preferences");
  $("#goStudy").onclick = () => go("#/study");
  $("#goStudy2").onclick = () => go("#/study");
  $("#goQuiz").onclick = () => go("#/quizzes");
  $("#goQuiz2").onclick = () => go("#/quizzes");
}

function profileSummary(type, p) {
  const rows =
    type === "student"
      ? [
          ["Education", p.education_level ? labelize(p.education_level) : null],
          ["Stream", p.stream],
          ["Subjects", taglist(p.subjects)],
          ["Target exams", taglist(p.target_exams)],
          ["Preferred colleges", taglist(p.preferred_colleges)],
        ]
      : [
          ["Experience", p.experience_years != null ? `${p.experience_years} yrs` : null],
          ["Role", p.role],
          ["Industry", p.industry],
          ["Skills", taglist(p.skills)],
          ["Goal", p.goal],
        ];
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

const PROTECTED = ["#/onboarding", "#/preferences", "#/dashboard", "#/study", "#/quizzes"];

async function render() {
  const hash = location.hash || (getToken() ? "#/dashboard" : "#/signin");
  // #/quiz/<id> and #/quiz/<id>/result are dynamic (and protected) too.
  const isProtected = PROTECTED.includes(hash) || hash.startsWith("#/quiz/");

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

  switch (hash) {
    case "#/signup": return renderSignup();
    case "#/signin": return renderSignin();
    case "#/onboarding": return renderOnboarding();
    case "#/preferences": return renderPreferences();
    case "#/dashboard": return renderDashboard();
    case "#/study": return renderStudy();
    case "#/quizzes": return renderQuizzes();
    default: return go(getToken() ? "#/dashboard" : "#/signin");
  }
}

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", render);
render();
