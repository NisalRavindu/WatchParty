# WatchParty

[![CI](https://github.com/NisalRavindu/WatchParty/actions/workflows/ci.yml/badge.svg)](https://github.com/NisalRavindu/WatchParty/actions/workflows/ci.yml)

A web app that makes choosing a movie meaningful and fun, for a watch party or a night alone. Instead of a black-box recommendation feed, it learns your taste from what you do: the movies you shortlist, the ones you pick, and small games like head-to-head brackets.

> Work in progress. Today it's a single-user local app.

## What it does

- **Search that understands movies**: by title, person (actor or director), keyword/theme, or studio.
  - Combine and exclude terms: `alien + small town -horror`, `disney + pixar`, `dreamworks -dreamworks animation`
  - Filter by genre, years and language, and sort by relevance, date, rating or title
  - Video extras, placeholder entries and "Self" appearances are filtered out
- **One status per movie**: Seen, Want to watch (Rewatch if already seen) or Curious, without separate lists to maintain.
- **Tonight sessions**: shortlist candidates for a session and lock in the pick.
- **Tonight's mood** (optional): mark a few "like this" / "not this" example movies to give the session context for suggestions.
- **Bracket game**: 8-movie knockout brackets on a topic ("Better ending", "More fun to rewatch", or your own). Playing a movie marks it as seen; "Haven't seen it" swaps in a stand-in, so Seen fills up without a chore.
  - Rankings come from a **Bradley-Terry model** fitted to every matchup, with uncertainty (MAP + Laplace approximation). Each movie shows a confidence band, not a falsely precise rank.
  - Round-one matchups are chosen to be the most informative: close strengths and uncertain movies first. Elo stays in the code as the simple baseline.
- **Signal log**: every interaction (matchup, shortlist, pick, status change, mood example) is stored as a signal, and rankings and preferences are derived from it.

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

You need a free TMDB API key. Copy `backend/.env.example` to `backend/.env` and put your key in it.

**With Docker:**

```bash
docker build -t watchparty .
docker run -p 8000:8000 --env-file backend/.env -v watchparty-data:/data watchparty
```

**Without Docker** (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app
```

Open http://localhost:8000.

Every push runs the linter (`ruff check .`, `ruff format --check .`), the tests (`pytest`), and a build and smoke test of the Docker image in GitHub Actions.

---

This product uses the TMDB API but is not endorsed or certified by TMDB.
