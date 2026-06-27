# Frontend — minimal SPA (zero build)

A small, good-looking single-page app for the Phase 1 journey: **sign up, sign in,
profile (student / working professional branch), preferences, and a dashboard**.

It's deliberately **framework-free and build-free** — just three files
(`index.html`, `styles.css`, `app.js`) talking to the FastAPI backend over `fetch`
with a Bearer JWT kept in `localStorage`. This keeps the UI throwaway-cheap until
the product is (maybe) re-developed against the company website with **Next.js**
(see `docs/ARCHITECTURE.md`).

## Run it

The backend must be running first (see the root `README.md`): `http://localhost:8000`.

Then serve these static files from any web server. The simplest:

```bash
cd frontend
python3 -m http.server 3000
```

Open **http://localhost:3000**. The backend's CORS is permissive in dev, so the
two origins talk to each other fine.

> You can also just open `index.html` directly, but a local server is cleaner.

## Pointing at a different API

Defaults to `http://localhost:8000`. To override without editing code, run this in
the browser console once:

```js
localStorage.setItem("sj_api", "http://your-host:8000"); location.reload();
```

## What it does

- **Sign up** → since the email-sending engine is deferred to Phase 5, the app
  auto-verifies using the token the API returns and logs you straight in.
- **Onboarding** → pick *Student* or *Working professional*; the form branches.
  Switching type later replaces the old profile (the backend enforces this).
- **Preferences** → topics, goal, cadence, difficulty, notifications.
- **Dashboard** → a summary of everything (`GET /users/me/profile` aggregate).

## Files
- `index.html` — app shell (one `<div id="app">`)
- `styles.css` — the whole design system
- `app.js` — API client, hash router, and all views
