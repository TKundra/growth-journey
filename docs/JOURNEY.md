# User Journey — what's built today (Phases 1–2)

> A deep, text/ASCII walkthrough of the **complete journey as currently
> implemented** — every screen, what happens **on click**, which **API** is
> called, the **exact request/response JSON**, what the **AI generates**, and
> what gets **stored**. Covers both branches — **Student** and **Working
> professional**.
>
> **Legend**
> `▢ screen`  `→ click/action`  `⇄ HTTP call`  `⚙ backend logic`  `🤖 AI`  `🗄 DB`
> `📥 input`  `📤 output`  `✅ built`  `🔜 later phase`
>
> All examples use placeholder UUIDs/timestamps. `public_id` is a UUIDv7 (the only
> id that leaves the system); the internal integer `id` is never exposed.

---

## 0. The whole map

```
   ┌──────────────────────────── NOT SIGNED IN ─────────────────────────────┐
   │   ▢ #/signup ───────────────► ▢ #/signin                               │
   │       │  create account             │  log in                          │
   │       └──────────────┬──────────────┘                                  │
   └──────────────────────┼─────────────────────────────────────────────────┘
                          │  JWT issued → saved in localStorage("sj_token")
                          ▼
   ┌──────────────────────────── SIGNED IN (Bearer JWT) ────────────────────┐
   │                                                                        │
   │   routeAfterAuth() sends you to the FIRST UNFINISHED step:             │
   │                                                                        │
   │     no user_type?  ─────────────────────► ▢ #/onboarding               │
   │     no preferences? ────────────────────► ▢ #/preferences              │
   │     else ───────────────────────────────► ▢ #/dashboard                │
   │                                                                        │
   │   ▢ #/onboarding ─ pick type ─┬─ 🎓 Student form ──┐                   │
   │                               └─ 💼 Pro form ───────┤                  │
   │                                                     ▼                  │
   │   ▢ #/preferences ──────────────────────────────────► ▢ #/dashboard    │
   │                                                       │                │
   │                                                       ▼                │
   │   ▢ #/study  ┌─ Discover  : ✦ Generate → cards → Save                  │
   │              └─ My library: saved cards + semantic search              │
   │                                                                        │
   │   🔜 Quizzes · Courses · Emails · Mock test · Mock interview           │
   └────────────────────────────────────────────────────────────────────────┘
```

**State the SPA keeps** (`frontend/app.js`):
```
localStorage.sj_token   = "<JWT>"           // sent as Authorization: Bearer <JWT>
state = { user, profile, preferences }      // hydrated from GET /users/me/profile
```

---

## 1. Sign up & sign in  ✅

### 1.1 Flow

```
▢ #/signup   (full name optional · email · password ≥ 8)
   │
   → click "Create account"
   │
   1. ⇄ POST /auth/signup        ⚙ bcrypt-hash password · 🗄 INSERT users
   │      📤 returns email_verification_token (until email engine, Phase 5)
   │
   2. ⇄ POST /auth/verify-email  ⚙ 🗄 is_email_verified=true, token cleared
   │      (SPA auto-verifies with the token from step 1 — dev convenience)
   │
   3. ⇄ POST /auth/login         ⚙ verify password · mint JWT (HS256, sub=public_id)
   │      📤 { access_token }    → saved to localStorage
   │
   └─ routeAfterAuth() → ▢ #/onboarding   (brand-new user has no user_type)
```

### 1.2 Example — `POST /auth/signup`

```
📥 Request
{
  "email": "riya@example.com",
  "password": "studyhard123",
  "full_name": "Riya Sharma"
}

📤 201 Created
{
  "public_id": "019f0a1b-2c3d-7e4f-8a9b-0c1d2e3f4a5b",
  "email": "riya@example.com",
  "full_name": "Riya Sharma",
  "user_type": null,                         ← not chosen yet
  "is_email_verified": false,
  "created_at": "2026-06-27T09:00:00Z",
  "email_verification_token": "7b1c9d2e-aaaa-7bbb-8ccc-1d2e3f4a5b6c"
}

✗ 409 Conflict  → { "detail": "An account with this email already exists" }
```

### 1.3 Example — `POST /auth/verify-email`

```
📥 { "token": "7b1c9d2e-aaaa-7bbb-8ccc-1d2e3f4a5b6c" }

📤 200 OK   (UserOut, now verified)
{ "public_id": "019f0a1b-…", "email": "riya@example.com",
  "full_name": "Riya Sharma", "user_type": null,
  "is_email_verified": true, "created_at": "2026-06-27T09:00:00Z" }

✗ 400  → { "detail": "Invalid or already-used verification token" }
```

### 1.4 Example — `POST /auth/login`  (also the whole of `▢ #/signin`)

```
📥 { "email": "riya@example.com", "password": "studyhard123" }

📤 200 OK
{ "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWI…", "token_type": "bearer" }

✗ 401  → { "detail": "Incorrect email or password" }
```

The token is a JWT: header `{alg:HS256}`, payload `{ sub:"<public_id>", exp:<+24h> }`.
Every protected call sends `Authorization: Bearer <access_token>`.

> 🤖 No AI in this whole section. `password_hash` is never returned.

---

## 2. Onboarding — who are you?  ✅   `▢ #/onboarding`

### 2.1 Flow (branching)

```
▢ "Tell us about yourself"
   │
   → click a type card        (state: chosen = "student" | "professional")
   │
   ├─🎓 STUDENT branch                       ┌─💼 PROFESSIONAL branch
   │   • education level  (select)           │   • experience_years (number)
   │   • stream           (text)             │   • role             (text)
   │   • subjects         [chips]            │   • industry         (text)
   │   • target exams     [chips]            │   • skills           [chips]
   │   • preferred colleges [chips]          │   • goal             (textarea)
   │                                         │
   └────────────────┬────────────────────────┘
                    │  → click "Save & continue →"
                    ▼
   ⇄ PUT /users/me/profile      (body discriminated on user_type)
   ⚙ Pydantic validates ONLY that branch's fields
     upsert profiles_student  XOR  profiles_professional
        └─ on type switch: DELETE the other branch's row (they never coexist)
   📤 returns the full aggregate { user, profile, preferences }
   │
   └─► ▢ #/preferences
```

How `user_type` flips and the data model branches:

```
                         users.user_type
                        ┌──────┴───────┐
            "student" ◄─┤   set here   ├─► "professional"
                        └──────────────┘
        profiles_student  ◄── 1:1 ──►  (none)
        (or, after switch) (none)  ◄── 1:1 ──►  profiles_professional
```

### 2.2 Example — 🎓 Student  `PUT /users/me/profile`

```
📥 Request (Authorization: Bearer <JWT>)
{
  "user_type": "student",
  "education_level": "undergraduate",
  "stream": "Science",
  "subjects": ["Physics", "Calculus"],
  "target_exams": ["JEE"],
  "preferred_colleges": ["IIT Bombay"]
}

📤 200 OK   (ProfileAggregateOut)
{
  "user": {
    "public_id": "019f0a1b-…", "email": "riya@example.com",
    "full_name": "Riya Sharma", "user_type": "student",
    "is_email_verified": true, "created_at": "2026-06-27T09:00:00Z"
  },
  "profile": {
    "public_id": "019f0a2c-…",
    "education_level": "undergraduate",
    "stream": "Science",
    "subjects": ["Physics", "Calculus"],
    "target_exams": ["JEE"],
    "preferred_colleges": ["IIT Bombay"],
    "updated_at": "2026-06-27T09:01:00Z"
  },
  "preferences": null                        ← not set yet
}
```

### 2.3 Example — 💼 Professional  `PUT /users/me/profile`

```
📥 Request
{
  "user_type": "professional",
  "experience_years": 5,
  "role": "Backend Engineer",
  "industry": "Fintech",
  "skills": ["Python", "SQL", "Kubernetes"],
  "goal": "Become a tech lead within a year"
}

📤 200 OK   (profile branch differs from the student one)
{
  "user": { …, "user_type": "professional" },
  "profile": {
    "public_id": "019f0a3d-…",
    "experience_years": 5,
    "role": "Backend Engineer",
    "industry": "Fintech",
    "skills": ["Python", "SQL", "Kubernetes"],
    "goal": "Become a tech lead within a year",
    "updated_at": "2026-06-27T09:02:00Z"
  },
  "preferences": null
}
```

> 🤖 No AI yet — but this profile is the **fallback fuel** for the AI: if the user
> sets no preference topics, the engine derives topics from
> `subjects/target_exams/stream` (student) or `skills/role/industry` (professional).

---

## 3. Preferences — tune the journey  ✅   `▢ #/preferences`

### 3.1 Flow

```
▢ "Your learning preferences"
   • topics              [chips]   ← PRIMARY signal for the AI
   • goal                (text, optional)
   • cadence  ◉ none  ○ daily  ○ weekly      ← used by Phase 3 scheduling
   • difficulty ◉ beginner ○ intermediate ○ advanced   ← AI query hint
   • notifications  [✓ on/off]
   │
   → "Save preferences →"     (or "Skip for now" → straight to dashboard)
   │
   ⇄ PUT /preferences/me
   🗄 upsert preferences (one row per user)
   │
   └─► ▢ #/dashboard
```

### 3.2 Example — `PUT /preferences/me`

```
📥 Request
{
  "topics": ["Calculus", "Physics"],
  "goal": "Crack JEE 2027",
  "cadence": "daily",
  "difficulty": "beginner",
  "notifications_enabled": true
}

📤 200 OK   (PreferencesOut)
{
  "public_id": "019f0a4e-…",
  "topics": ["Calculus", "Physics"],
  "goal": "Crack JEE 2027",
  "cadence": "daily",
  "difficulty": "beginner",
  "notifications_enabled": true,
  "updated_at": "2026-06-27T09:03:00Z"
}

✗ GET /preferences/me before any save → 404 { "detail": "No preferences set yet" }
```

---

## 4. Dashboard — your home  ✅   `▢ #/dashboard`

### 4.1 Flow

```
⇄ GET /users/me/profile   →  ONE aggregate call hydrates the whole screen
   │
   ▢ Dashboard
     ┌──────────────────────────────────────────────────────────────┐
     │  Welcome back, Riya 👋                   [ ✓ Email verified ]│  ← badge
     │  "Your study journey, all in one place."                     │  ← adapts
     ├──────────────────────────────────────────────────────────────┤
     │  Your profile                                    [ Edit ]────┼─► #/onboarding
     │   Education · Stream · Subjects · Target exams · Colleges    │
     ├──────────────────────────────────────────────────────────────┤
     │  Learning preferences                            [ Edit ]────┼─► #/preferences
     │   Topics · Goal · Cadence · Difficulty · Notifications       │
     ├──────────────────────────────────────────────────────────────┤
     │  Study material                                  [ Open ]────┼─► #/study
     │   [ Browse study material → ]────────────────────────────────┼─► #/study
     └──────────────────────────────────────────────────────────────┘
   sidebar: 🏠 Dashboard · 📚 Study material · 📝 Quizzes (Soon 🔜)
```

The tagline + badge adapt to the user:
```
user_type = professional → "Your upskilling journey, all in one place."
user_type = student      → "Your study journey, all in one place."
is_email_verified=false  → amber "● Not verified" badge instead of green ✓
```

### 4.2 Example — `GET /users/me/profile` (student, fully set up)

```
📤 200 OK
{
  "user":        {
                    "public_id": "019f0a1b-…",
                    "email": "riya@example.com",
                    "full_name": "Riya Sharma",
                    "user_type": "student",
                    "is_email_verified": true,
                    "created_at": "2026-06-27T09:00:00Z"
                 },
  "profile":     {
                    "education_level": "undergraduate",
                    "stream": "Science",
                    "subjects": ["Physics","Calculus"],
                    "target_exams": ["JEE"],
                    "preferred_colleges": ["IIT Bombay"],
                    "updated_at": "…"
                 },
  "preferences": {
                    "topics": ["Calculus","Physics"],
                    "goal": "Crack JEE 2027",
                    "cadence": "daily",
                    "difficulty": "beginner",
                    "notifications_enabled": true,
                    "updated_at":"…"
                 }
}
```

---

## 5. Study material — the AI engine  ✅   `▢ #/study`

Two sub-tabs. **Discover** = generate + browse + save. **My library** = saved
items + semantic search.

### 5.0 Default view — what shows when you open `#/study`

```
open ▢ #/study   →  studyTab defaults to "Discover"
   │
   ⇄ GET /study-material            ← loads your PREVIOUSLY generated feed
   │     (study_resources is persisted per user → survives logout/login)
   │
   ├─ feed has items ──►  render the cards (each with its live is_saved flag)
   │
   └─ feed is EMPTY ───►  empty-state prompt (NO AI is called on open):
        ┌────────────────────────────────────────────┐
        │                  📚                        │
        │          No study material yet             │
        │  Hit Generate and we'll search the web and │
        │  curate the best resources for your topics.│
        └────────────────────────────────────────────┘
```

**Key points**
- Opening the page is **read-only** — it never auto-generates (no AI cost/latency
  on every visit). Curation runs **only** when you click **✦ Generate**.
- Because the feed is stored in `study_resources`, returning users see their last
  curated set immediately; re-running Generate refreshes/extends it (dedup by URL).
- An empty `📤 []` from `GET /study-material` is the trigger for the empty state —
  not an error.

### 5.1 Populated view (after at least one Generate)

```
┌─ Study material ────────────────────────────────────────────────────────┐
│  [ Discover ]  [ My library ]  topics: Calculus  Physics     ✦ Generate │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌──────────────────┐  ┌────────────────┐           │
│  │ 📄 DOCS ★ 95   │  │ 🧩 TUTORIAL ★ 88 │  │ 🎬 VIDEO ★ 80  │           │
│  │ Khan — Limits  │  │ Paul's Notes     │  │ 3Blue1Brown    │           │
│  │ short summary… │  │ short summary…   │  │ short summary… │           │
│  │ khanacad..·30m │  │ tutorial.math    │  │ youtube · 18m  │           │
│  │ #calculus      │  │ #limits          │  │ #intuition     │           │
│  │ [Open ↗][Save] │  │ [Open ↗][Save]   │  │ [Open ↗][Save] │           │
│  └────────────────┘  └──────────────────┘  └────────────────┘           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5a. Generate — the curation pipeline

```
→ click  ✦ Generate
│
⇄ POST /study-material/generate     📥 {}  (empty = use my profile+preferences)
│
▼ ════════════════ INSIDE THE BACKEND ════════════════════════════════════════

 ⚙ STEP 1 — Query builder            query_builder.resolve_topics + build_queries
    topics = overrides ?: preference.topics ?: profile-derived
    ┌─────────────────────────────────────────────────────────────────┐
    │ ["Calculus","Physics"]  + difficulty "beginner"                 │
    │   → "Calculus learn tutorial guide for beginners introduction…" │
    │   → "Physics  learn tutorial guide for beginners introduction…" │
    └─────────────────────────────────────────────────────────────────┘
    ✗ no topics anywhere → 422

 ⚙ STEP 2 — Web search               curator.gather_candidates
    each query → 🌐 SearXNG (self-hosted metasearch)  ──(error)──►  🌐 DuckDuckGo (fallback)
    (web category for articles/docs + videos category for YouTube)
    flatten + dedupe by URL →
    ┌─ candidates ─────────────────────────────────────────────────────┐
    │ {title:"Khan Academy: Limits", url:"https://khanacademy.org/…",  │
    │  snippet:"Learn what a limit is…", topic:"Calculus"}             │
    │ {title:"Paul's Online Notes", url:"https://tutorial.math.lamar…",│
    │  snippet:"Calculus I notes…",   topic:"Calculus"}  … (N more)    │
    └──────────────────────────────────────────────────────────────────┘
    ✗ search returns nothing → 502

 🤖 STEP 3 — LLM curation            curator.curate  (Ollama, "default" tier)
    📥 to the model:  system="curate learning resources, ONLY real candidate URLs"
                      user = the candidate list + difficulty
    📤 from the model:  structured JSON validated to the schema →
    ┌─ items[] ───────────────────────────────────────────────────────┐
    │ { "title":"Khan Academy: Introduction to Limits",               │
    │   "url":"https://khanacademy.org/math/calculus-1/limits",       │
    │   "summary":"A gentle, visual intro to limits — ideal first…",  │
    │   "topic":"Calculus", "tags":["limits","intro"],                │
    │   "difficulty":"beginner", "kind":"video",                      │
    │   "est_minutes":25, "relevance":95                              │
    │ }                                                               │
    └─────────────────────────────────────────────────────────────────┘
    🛡 GUARDRAIL: drop any item whose URL was NOT in the candidates
                  (kills hallucinated links — every item is a real source)
    ✗ OLLAMA_API_KEY missing → 503

 🗄 STEP 4 — Persist                  repository.upsert_resources
    INSERT into study_resources (per user) …
    ON CONFLICT (user_id, url) DO UPDATE   ← re-Generate dedupes, never piles up
▲ ════════════════════════════════════════════════════════════════════════════
│
📤 returns { generated, resources:[…] }  → cards render
```

**Example — `POST /study-material/generate`**

```
📥 Request   {}                        (or override: {"topics":["Limits"],
                                         "difficulty":"intermediate","per_topic":5})

📤 200 OK
{
  "generated": 2,
  "resources": [
    {
      "public_id": "019f0b01-…",
      "title": "Khan Academy: Introduction to Limits",
      "url": "https://www.khanacademy.org/math/calculus-1/limits",
      "source_domain": "khanacademy.org",
      "summary": "A gentle, visual introduction to limits — a solid first stop.",
      "topic": "Calculus",
      "tags": ["limits", "intro"],
      "difficulty": "beginner",
      "kind": "video",
      "est_minutes": 25,
      "relevance": 95,
      "is_saved": false,
      "created_at": "2026-06-27T09:05:00Z"
    },
    {
      "public_id": "019f0b02-…",
      "title": "Paul's Online Notes — Calculus I",
      "url": "https://tutorial.math.lamar.edu/classes/calci/calci.aspx",
      "source_domain": "tutorial.math.lamar.edu",
      "summary": "Clear written notes with worked examples across Calculus I.",
      "topic": "Calculus",
      "tags": ["notes", "examples"],
      "difficulty": "beginner",
      "kind": "docs",
      "est_minutes": 120,
      "relevance": 88,
      "is_saved": false,
      "created_at": "2026-06-27T09:05:00Z"
    }
  ]
}

✗ 422 { "detail":"No topics to study. Set preferences/profile or pass `topics`." }
✗ 502 { "detail":"Web search returned no results. Check the search provider/network." }
✗ 503 { "detail":"AI is not configured (set OLLAMA_API_KEY) — study material is unavailable." }
```

**Browse the feed — `GET /study-material`** → returns the array above (each with a
live `is_saved` flag), ranked `relevance desc, created_at desc`.

### 5b. Save to library (+ quiet RAG indexing)

```
▢ card → click "Save"
│
⇄ POST /study-material/{public_id}/save      📥 { "note": "start here" }
🗄 INSERT saved_resources (promote feed item → library)
│
⚙ best-effort RAG indexing            rag.index_saved_resource
   text = title + " — " + summary
   ├─ chunk_text() → word-boundary chunks
   ├─ 🤖 embed chunks (Ollama, 768-dim)
   └─ 🗄 store vectors in resource_chunks (pgvector)
   ↳ no key / failure → SILENTLY skipped (the save still succeeds)
│
📤 card flips to "✓ Saved"; feed's is_saved updates
```

**Example — `POST /study-material/{id}/save`**

```
📥 { "note": "start here" }            (note optional → {} is fine)

📤 200 OK   (SavedResourceOut: the saved-row shell + nested resource)
{
  "public_id": "019f0c10-…",           ← the saved_resources row id
  "note": "start here",
  "created_at": "2026-06-27T09:06:00Z",
  "resource": {
    "public_id": "019f0b01-…",         ← the study_resources row
    "title": "Khan Academy: Introduction to Limits",
    "url": "https://www.khanacademy.org/math/calculus-1/limits",
    "source_domain": "khanacademy.org",
    "summary": "A gentle, visual introduction to limits…",
    "topic": "Calculus", "tags":["limits","intro"],
    "difficulty":"beginner", "kind":"video",
    "est_minutes":25, "relevance":95,
    "is_saved": true,
    "created_at":"2026-06-27T09:05:00Z"
  }
}

✗ 404 { "detail":"Resource not found" }   (unknown id)

— Remove: DELETE /study-material/{id}/save → 204 No Content
          ✗ 404 { "detail":"Not in library" }
```

### 5c. My library — browse + semantic search

```
▢ Study material ▸ My library
   ⇄ GET /study-material/library      → your saved resources (as cards)
   │
   search box → type "rate of change" → "Search"
   ⇄ GET /study-material/library/search?q=rate%20of%20change&k=5
   🤖 embed the query (Ollama)                 rag.semantic_search
   🗄 cosine search over resource_chunks  (pgvector  <=>  operator)
   └─ ranked nearest saved resources, each with a 0–1 score
```

**Example — `GET /study-material/library`**

```
📤 200 OK
[
  { "public_id":"019f0c10-…", "note":"start here",
    "created_at":"2026-06-27T09:06:00Z",
    "resource": { "public_id":"019f0b01-…",
                  "title":"Khan Academy: Introduction to Limits",
                  "url":"https://www.khanacademy.org/…", "is_saved":true, … } }
]
```

**Example — `GET /study-material/library/search?q=rate of change`**

```
📤 200 OK   (SemanticHit[] — score = cosine similarity, 1.0 = closest)
[
  { "score": 0.83,
    "resource": { "public_id":"019f0b01-…",
                  "title":"Khan Academy: Introduction to Limits",
                  "topic":"Calculus", "is_saved":true, … } }
]

✗ 503 { "detail":"AI is not configured (set OLLAMA_API_KEY) — study material is unavailable." }
       (semantic search embeds the query on OLLAMA_EMBED_HOST — the local Ollama must be reachable)
```

---

## 5.5 Deep dive — how the AI **curates** and how **saving** builds the RAG index

This zooms all the way in on the two AI moments: **curation** (Generate) and
**embedding-on-save** (Save → semantic search). Same data, shown morphing stage
by stage.

### A) Curation — raw web hits → ranked, grounded study cards

```
                          curator.curate()  +  LLMClient.parse()   (ai_core/llm.py)

  ┌── INPUT: candidates (messy web search results) ─────────────────────────────┐
  │  [                                                                          │
  │    {title:"Limits | Khan Academy", url:"khanacademy.org/…/limits",          │
  │     snippet:"Learn what a limit is and how to evaluate…", topic:"Calculus"},│
  │    {title:"Limit (mathematics) - Wikipedia", url:"en.wikipedia.org/…",      │
  │     snippet:"In mathematics, a limit is the value…", topic:"Calculus"},     │
  │    {title:"Khan Academy Limits (dup)", url:"khanacademy.org/…/limits",      │ ← dup URL
  │     snippet:"…", topic:"Calculus"},  … (up to per_topic × #topics)          │
  │  ]                                                                          │
  └─────────────────────────────────────────────────────────────────────────────┘
        │
        │  1. dedupe by URL already done in gather_candidates()
        │  2. remember the allowed set:  allowed = { every candidate.url }
        ▼
  ┌── PROMPT assembled by curator._prompt() ────────────────────────────────────┐
  │  system: "You are a learning-resource curator. … Deduplicate …, rank …,     │
  │           write a short why-it-matters summary … CRITICAL: only use URLs    │
  │           that appear in the provided candidates — never invent a URL."     │
  │  user:   "Learner difficulty preference: beginner.                          │
  │           Return at most 12 resources, best first, as the `items` array.    │
  │           Candidates (title — url — topic — snippet):                       │
  │           1. Limits | Khan Academy — khanacademy.org/… — [Calculus] — …     │
  │           2. Limit (mathematics) - Wikipedia — en.wikipedia.org/… — …       │
  │           3. …"                              (snippet trimmed to 300 chars) │
  └─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼  🤖 Ollama  (tier "default" = gpt-oss:120b)
           parse() sends  format = Curation.model_json_schema()
           → the model is CONSTRAINED to emit JSON matching the schema, not prose
  ┌── RAW MODEL OUTPUT (already valid JSON, validated → Curation pydantic) ──────┐
  │  { "items": [                                                                │
  │      {title:"Khan Academy: Introduction to Limits",                          │
  │       url:"khanacademy.org/…/limits", summary:"A gentle visual intro…",      │
  │       topic:"Calculus", tags:["limits","intro"], difficulty:"beginner",      │
  │       kind:"video", est_minutes:25, relevance:95},                           │
  │      {title:"Limit (mathematics)", url:"en.wikipedia.org/…",                 │
  │       …, relevance:60},                                                      │
  │      {title:"Best Calculus Course", url:"some-blog.com/promo",  ◄── NOT a    │
  │       …, relevance:99}                            candidate URL (invented)   │
  │  ]}                                                                          │
  └──────────────────────────────────────────────────────────────────────────────┘
        │
        ▼  🛡 GUARDRAIL:  keep item only if item.url ∈ allowed
  ┌── GROUNDED items (hallucinated "some-blog.com/promo" DROPPED) ──────────────┐
  │  [ Khan (95) , Wikipedia (60) ]      then  [:limit]  (cap at 12)            │
  └─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼  🗄 repository.upsert_resources()  — two upserts each (canonical + per-user)
  ┌── resources (canonical, shared) + feed_items (per-user) ─────────────────────┐
  │  1) INSERT resources (url, title, source_domain, summary, tags,             │
  │            difficulty, kind, est_minutes)                                    │
  │     ON CONFLICT (url) DO UPDATE …      ← URL deduped GLOBALLY across users   │
  │     RETURNING id                                                            │
  │  2) INSERT feed_items (user_id, resource_id, topic, relevance)              │
  │     ON CONFLICT (user_id, resource_id) DO UPDATE …  ← re-Generate refreshes │
  │  → re-read joined row (is_saved = EXISTS check against saved_resources)      │
  └─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼  list ordered by relevance DESC, created_at DESC  →  cards on screen
```

**Why each guard exists**

```
 schema-constrained output  → no "parse the prose" fragility; always valid JSON
 URL-in-candidates guard    → every card links to a REAL page the search found
 ON CONFLICT (user_id,url)  → Generate is idempotent per URL; feed never bloats
 source_domain derived      → trustworthy "where it's from" label, not model-claimed
```

### B) Save → embed → store — building the searchable library (RAG)

Saving does two things: a **durable promotion** (always) and a **best-effort
vector index** (only if embeddings are configured).

```
▢ card → "Save"     ⇄ POST /study-material/{id}/save   { "note": "start here" }
   │
   ├─ 🗄 ALWAYS:  INSERT saved_resources (user_id, resource_id, note)
   │             ON CONFLICT (user_id, resource_id) DO UPDATE note
   │             → this is the library; survives even with no AI key
   │
   └─ ⚙ BEST-EFFORT:  rag.index_saved_resource()   (never breaks the save)
         │
         │  body = title + " — " + summary
         │  "Khan Academy: Introduction to Limits — A gentle visual intro to limits…"
         ▼
      chunk_text(size=800, overlap=100)        word-boundary safe
         │  short text → 1 chunk;  long text → overlapping windows:
         │     [────────chunk 0────────]
         │                       [────────chunk 1────────]   ← 100-char overlap
         ▼
      🤖 LLMClient.embed(chunks)   (local OLLAMA_EMBED_HOST, "nomic-embed-text", 768-dim)
         │   "…intro to limits…"  →  [0.0123, -0.0456, 0.0789, … ] (768 floats)
         ▼
      🗄 repository.replace_chunks()
         DELETE old chunks for this resource, then INSERT each:
         ┌── resource_chunks ────────────────────────────────────────────────┐
         │ resource_id │ chunk_index │ content            │ embedding        │
         │  (FK)       │     0       │ "Khan… limits…"    │ '[0.0123,-0.04…]'│ vector(768)
         └───────────────────────────────────────────────────────────────────┘
         (UNIQUE(resource_id, chunk_index); IVFFlat cosine index on embedding)

   ↳ embed host unreachable / embed error → indexing SILENTLY skipped; save still 200 OK
     (embeddings use OLLAMA_EMBED_HOST, not the cloud — Ollama Cloud has no embed model)
```

### C) Reading it back — semantic search over the library

```
search box "rate of change"
   ⇄ GET /study-material/library/search?q=rate of change&k=5
   │
   ▼  rag.semantic_search()
   🤖 embed(["rate of change"])[0]   →  query vector  q = [ … 768 floats … ]
   │
   ▼  repository.search_saved_chunks()   (pgvector  <=>  = cosine distance)
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ SELECT  resource…,  1 - (c.embedding <=> q)  AS score                    │
   │ FROM resource_chunks c                                                   │
   │ JOIN resources res ON res.id = c.resource_id                            │
   │ JOIN saved_resources s ON s.resource_id = res.id AND s.user_id = me      │ ← only MY saved
   │ JOIN feed_items f ON f.resource_id = res.id AND f.user_id = me           │ ← my topic/rank
   │ WHERE c.embedding IS NOT NULL                                            │
   │ ORDER BY c.embedding <=> q      (nearest first)                          │
   │ LIMIT 5                                                                  │
   └──────────────────────────────────────────────────────────────────────────┘
   │
   ▼  vector space intuition (cosine: closer angle = more related)
        "rate of change" •           • "Introduction to Limits"   score 0.83  ✅ near
                                 • "Limit (mathematics)"          score 0.71
                         •  "Photosynthesis basics"               score 0.12  ✗ far
   │
   📤 [ { score:0.83, resource:{ title:"…Introduction to Limits", … } }, … ]
```

**The full data lifecycle, end to end**

```
 web snippet ──curate──► resources row  ──+feed_item──► save ──► saved_resources row
     (text)              (canonical,         (per-user        (in your library)
                          shared by url)      topic+rank)            │
                               │                                     │
                               └────── title+summary ────────────────┘
                                          │
                                       embed (768-d)   ← once per URL, shared across users
                                          ▼
                                   resource_chunks.embedding  ──cosine query──► ranked hits
```

> 🔜 Phase 3 reuses exactly this `resource_chunks` index: MCQ generation will
> retrieve a user's saved material as context, and a future "chat with your
> material" will do the same cosine lookup.

---

## 6. Two end-to-end walkthroughs

### 🎓 Riya — student prepping for JEE

```
signup ─► verify ─► login
  │  POST /auth/signup → token → POST /auth/verify-email → POST /auth/login
  ▼
onboarding (student)
  │  PUT /users/me/profile { user_type:"student", subjects:["Physics","Calculus"],
  │                          target_exams:["JEE"], stream:"Science", … }
  ▼
preferences
  │  PUT /preferences/me { topics:["Calculus","Physics"],
  │                        difficulty:"beginner", cadence:"daily" }
  ▼
dashboard  →  study material  →  ✦ Generate
  │  POST /study-material/generate {}
  │   ⚙ queries: "Calculus … for beginners", "Physics … for beginners"
  │   🌐 search → 🤖 curate → 🗄 ~12 ranked resources w/ summaries+tags
  ▼
save "Khan Academy — Limits"
  │  POST /study-material/019f0b01-…/save { note:"start here" }
  │   🤖 embed → 🗄 resource_chunks (now searchable)
  ▼
library search "rate of change"
  │  GET /study-material/library/search?q=rate of change
  │   🤖 embed query → 🗄 cosine match → top saved resources
  ▼
🔜 (Phase 3) generate an MCQ quiz from these topics / saved material
```

### 💼 Karan — backend dev moving to tech lead

```
signup ─► verify ─► login
  ▼
onboarding (professional)
  │  PUT /users/me/profile { user_type:"professional", experience_years:5,
  │     role:"Backend Engineer", industry:"Fintech",
  │     skills:["Python","SQL","Kubernetes"], goal:"become a tech lead" }
  ▼
preferences
  │  PUT /preferences/me { topics:["System Design","Kubernetes"],
  │                        difficulty:"intermediate" }
  ▼
dashboard → study material → ✦ Generate
  │  POST /study-material/generate {}
  │   ⚙ queries from ["System Design","Kubernetes"] (intermediate)
  │   ── if he'd left topics EMPTY, the builder would fall back to his
  │      skills/role/industry: ["Python","SQL","Kubernetes","Backend Engineer"…]
  │   🌐 search → 🤖 curate → 🗄 ranked resources
  ▼
save the best → library → semantic search across them later
  ▼
🔜 (Phase 3) timed quizzes + per-topic progress analytics
```

> Same code path, different fuel: the only thing that differs between the two
> personas is **what feeds the query builder** (student academics vs professional
> skills). Everything downstream — search, curation, save, RAG — is identical.

---

## 7. Where AI is (and isn't) involved today

| Step | Endpoint | AI? | What the AI does |
|---|---|---|---|
| Sign up / verify / login | `/auth/*` | ❌ | — |
| Onboarding profile | `PUT /users/me/profile` | ❌ | feeds the AI later |
| Preferences | `PUT /preferences/me` | ❌ | feeds the AI later |
| Dashboard | `GET /users/me/profile` | ❌ | — |
| **Generate feed** | `POST /study-material/generate` | ✅ | curate: dedupe · rank · summarize · tag · cite (real URLs only) |
| **Save** | `POST /study-material/{id}/save` | ✅ | embed + index for RAG (best-effort) |
| **Library search** | `GET /study-material/library/search` | ✅ | embed query → cosine search over saved material |

**Needs `OLLAMA_API_KEY` (cloud):** Generate (curation). Without it, web search
still runs (SearXNG default, DuckDuckGo fallback), Generate returns a clean
**503**, and library search is unavailable — every non-AI step works fully.
**Needs `OLLAMA_EMBED_HOST` (local Ollama):** embeddings for Save-indexing and
library search. Ollama Cloud has no embedding model, so this is a separate host;
if it's unreachable, Save still succeeds (RAG indexing is skipped).

---

## 8. Data left behind (what's in Postgres after the journey)

```
users ─┬─< profiles_student      (1:1, student branch)
       ├─< profiles_professional  (1:1, professional branch)   ← only one branch exists
       ├─< preferences            (1:1)
       ├─< feed_items             (1:many — the per-user curated feed; UNIQUE(user_id,resource_id))
       └─< saved_resources        (1:many — library; FK→resources)

resources (CANONICAL, UNIQUE(url) — shared across all users; no user_id)
       ├─< feed_items             (many users can have the same resource in their feed)
       └─< resource_chunks        (1:many — pgvector embeddings; embedded ONCE per URL, shared)
```

---

## 9. Intentionally not built yet  🔜

```
Phase 3  Quiz / MCQ engine + daily/weekly tests   ← next; reads resource_chunks
Phase 4  Courses & certifications
Phase 5  Email / notification engine (real verification emails, digests, reminders)
Phase 6  Mock test (formal: sectional, timed, larger sets)
Phase 7  Mock interview (SEPARATE subsystem: stateful multi-turn + rubric eval)
Phase 8  Analytics, mastery graph, streaks, leaderboard
Phase 9  Hardening, observability, deploy & scale
```

See `docs/ROADMAP.md` for the checkbox plan and `docs/PROGRESS_LOG.md` for the
dated build history.

---

# Appendix — complete inventory of what's built (Phases 0–2)

A reference dump of *everything* that exists today, so nothing built is left out
of this doc. The journey above is the "why"; this is the "what".

## A. Every HTTP endpoint (15 routes)

```
SYSTEM / health
  GET    /                       service banner { service, docs }
  GET    /health                 liveness  → { status, version, env }
  GET    /health/db              readiness → runs `select 1` → { status, database }

AUTH                                                         (auth required?)
  POST   /auth/signup            create account              no   → 201 SignupOut
  POST   /auth/verify-email      confirm with token          no   → UserOut
  POST   /auth/login             email+password → JWT        no   → TokenOut
  GET    /auth/me                current user                YES  → UserOut

USERS / PROFILE
  PUT    /users/me/profile       set type + profile branch   YES  → ProfileAggregateOut
  GET    /users/me/profile       dashboard aggregate         YES  → ProfileAggregateOut

PREFERENCES
  PUT    /preferences/me         upsert preferences          YES  → PreferencesOut
  GET    /preferences/me         fetch (404 if unset)        YES  → PreferencesOut

STUDY MATERIAL (AI)
  POST   /study-material/generate          curate a feed     YES  → GenerateOut
  GET    /study-material                   list the feed     YES  → StudyResourceOut[]
  GET    /study-material/{public_id}       one resource      YES  → StudyResourceOut
  POST   /study-material/{public_id}/save  add to library    YES  → SavedResourceOut
  DELETE /study-material/{public_id}/save  remove            YES  → 204
  GET    /study-material/library           saved list        YES  → SavedResourceOut[]
  GET    /study-material/library/search    semantic search   YES  → SemanticHit[]
```

`GET /study-material/{public_id}` (single resource) and `GET /auth/me` (whoami)
exist and are used internally; the SPA mostly relies on the aggregate + list calls.

Interactive docs for all of the above: `http://localhost:8000/docs` (Swagger).

## B. AI core (`app/ai_core/`) — the shared machinery

```
LLM client (llm.py) — Ollama Cloud, one client built from OLLAMA_HOST+OLLAMA_API_KEY
  tiers → models:   cheap   = gpt-oss:20b        (bulk: MCQs, short summaries)
                    default = gpt-oss:120b       (curation, interviewer)   ← study uses this
                    smart   = deepseek-v3.1:671b (hard evaluation/scoring)
  embed  → nomic-embed-text (768-dim), via a SEPARATE client on OLLAMA_EMBED_HOST
           (local Ollama — the cloud serves no embedding model)   (RAG)
  entry points:
    complete(prompt, tier, system, options)            → free-form text
    parse(prompt, schema, …)                           → validated Pydantic object
       └─ TOLERANT: if the model wraps JSON in prose/```fences, _extract_json()
          slices it out and re-validates (handles gpt-oss not honoring `format`)
    embed(inputs)                                       → list[vector]
  LLMNotConfigured raised if no key → routers map to 503
  SWAP POINT: _build_client() is where the key-rotation service plugs in later

Search abstraction (search/) — provider-agnostic
  SearchProvider.search(query, max_results)        → [SearchResult{title,url,snippet}]
  SearchProvider.search_videos(query, max_results) → [SearchResult{…, kind:"video"}]
    SearxngProvider     (default, self-hosted metasearch — no key; web + videos)
    TavilyProvider      (optional, needs TAVILY_API_KEY)
    DuckDuckGoProvider  (keyless fallback)
  picked by SEARCH_PROVIDER; curator wraps these: try configured per-query
  → on ANY error fall back to DDG
```

**Curation robustness (built-in guards):**
```
1. schema-constrained request (format = Curation JSON schema)
2. prose/fence tolerance        → _extract_json() fallback in parse()
3. optional fields + backfill    → only `url` is required; title/topic/summary
                                    backfilled from the originating candidate
4. anti-hallucination guardrail  → drop any item whose URL wasn't a candidate
5. idempotent persist            → ON CONFLICT (user_id, url) DO UPDATE
```

## C. Data model & migrations (`app/db/`)

```
Convention (every table): internal `id bigint identity` PK  +  external
`public_id uuid (uuidv7) unique`  +  created_at/updated_at.  uuidv7() & the
set_updated_at() trigger are defined in the migrations.

Forward-only .sql migrations, applied by `python -m app.db.migrate`,
tracked in schema_migrations:
  0001_baseline.sql            uuidv7() generator
  0002_phase1_identity.sql     users, profiles_student, profiles_professional,
                               preferences  (+ set_updated_at trigger)
  0003_phase2_study_material.sql  vector extension; study_resources,
                               saved_resources, resource_chunks (pgvector + IVFFlat)
  0004_normalize_resources.sql split study_resources → canonical `resources`
                               (UNIQUE url, shared) + per-user `feed_items`;
                               repoint saved_resources/resource_chunks at the
                               canonical id → embed each URL once, reuse across users

Access: raw SQL via psycopg3, pooled dict_row connections (app/db/pool.py).
NO ORM (no SQLAlchemy/Alembic).
```

## D. Frontend (`frontend/`) — zero-build SPA

```
Files:   index.html · app.js · styles.css   (no node_modules, no bundler)
Serve:   python3 -m http.server 3000   (talks to API at http://localhost:8000)

Hash routes:  #/signup #/signin #/onboarding #/preferences #/dashboard #/study
Auth:    JWT in localStorage("sj_token"), sent as Authorization: Bearer …
State:   state = { user, profile, preferences }  (from GET /users/me/profile)
Theme:   "liquid glass" — glassmorphism over an animated gradient, Plus Jakarta
         Sans, neutral "Journey" brand (works for students AND professionals)
Pieces:  authShell · appShell(sidebar+content) · chipsInput · segmented control ·
         toast · resource cards · empty states · semantic-search box
```

## E. Tooling, tests & config

```
Tests (pytest, 27):  test_health · test_security · test_auth_flow ·
                     test_study_material_unit · test_study_material_flow
   DB-backed tests skip automatically if Postgres/migrations aren't present
   (the `requires_db` marker), so `pytest` stays green on a bare checkout.
Format:  black (line-length 100)        Lint hooks: pre-commit
Infra:   docker-compose → FastAPI api + self-hosted SearXNG. Postgres (pgvector)
         is external (point DATABASE_URL at it). NO Redis/queue yet (deferred).

Config (.env / pydantic-settings) — keys that exist today:
  APP_ENV · APP_DEBUG · APP_SECRET_KEY
  JWT_ALGORITHM (HS256) · ACCESS_TOKEN_EXPIRE_MINUTES (1 day)
  DATABASE_URL
  OLLAMA_HOST · OLLAMA_API_KEY                       (cloud: chat/curation)
  OLLAMA_EMBED_HOST · OLLAMA_EMBED_API_KEY           (local: embeddings/RAG)
  LLM_MODEL_CHEAP · LLM_MODEL_DEFAULT · LLM_MODEL_SMART · LLM_MODEL_EMBED
  SEARCH_PROVIDER (searxng|tavily|duckduckgo, default searxng)
  SEARXNG_URL · SEARXNG_TIMEOUT · TAVILY_API_KEY
  (.env is gitignored — secrets never committed)
```

## F. Module map (`app/modules/`)

```
BUILT:    auth · users · preferences · study_material
SCAFFOLD: courses · assessments · interviews · notifications · analytics
          (empty packages, wired in their phase — see §9)
```
