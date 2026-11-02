# WatchParty

A web app that makes choosing a movie meaningful and fun, for a watch party or a night alone. Instead of a black-box recommendation feed, it learns your taste from what you do: the movies you shortlist, the ones you pick, and small games like head-to-head brackets.

> Work in progress. Today it's a single-user local app.

## What it does

- **Search that understands movies**: by title, person (actor or director), keyword/theme, or studio.
  - Combine and exclude terms: `alien + small town -horror`, `disney + pixar`, `dreamworks -dreamworks animation`
  - Filter by genre, years and language, and sort by relevance, date, rating or title
  - Video extras, placeholder entries and "Self" appearances are filtered out
- **One status per movie**: Seen, Want to watch (Rewatch if already seen) or Curious, without separate lists to maintain.
- **Tonight sessions**: shortlist candidates for a session and lock in the pick.
- **Signal log**: every interaction (compare, shortlist, pick, status change) is stored as a signal, and preferences such as Elo rankings from brackets are derived from it.

## Stack

- **Backend:** Python, FastAPI, SQLModel on SQLite, httpx (async), pytest
- **Frontend:** plain HTML, CSS and JavaScript with no build step, served by FastAPI
- **Data:** [TMDB API](https://developer.themoviedb.org/)

The backend is a modular monolith: thin routers, services holding the logic, and pure functions for filtering, sorting and ranking so they're easy to test.

```
backend/
  app/
    routers/    HTTP layer: movies, library, sessions, games
    services/   search, TMDB client, studios, ranking, text helpers
    models.py   Movie, LibraryEntry, WatchSession, Signal
  tests/
frontend/       index.html, app.js, styles.css
```

## Run it locally

Requires Python 3.11+ and a free TMDB API key.

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your TMDB key in .env
uvicorn app.main:app
```

Open http://localhost:8000.

Run the tests with `pytest` from `backend/`.

---

This product uses the TMDB API but is not endorsed or certified by TMDB.
