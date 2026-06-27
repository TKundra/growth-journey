# Frontend (intentionally minimal — deferred)

The platform is **API-first** for now. The frontend is kept minimal on purpose:
this product may be re-developed against the company's official website later,
so we avoid over-investing in a throwaway UI.

For now:
- Use the interactive API docs at **http://localhost:8000/docs** to exercise the backend.
- When a real UI is needed, the recommended choice is **Next.js (React + TypeScript)**
  consuming the FastAPI backend (see `docs/ARCHITECTURE.md`).

No build tooling lives here yet by design.
