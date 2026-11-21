from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.config import LOCAL_USER_ID
from app.db import SessionDep
from app.models import Movie, SessionCandidate, SessionExample, Signal, SignalKind, WatchSession
from app.services.movies import ensure_movie

router = APIRouter(prefix="/sessions", tags=["sessions"])


class MovieRef(BaseModel):
    movie_id: int


class ExampleRef(MovieRef):
    positive: bool


class Example(BaseModel):
    movie: Movie
    positive: bool


class SessionDetail(BaseModel):
    session: WatchSession
    candidates: list[Movie]
    examples: list[Example]
    signals: list[Signal]


def get_or_404(session: SessionDep, session_id: int) -> WatchSession:
    watch_session = session.get(WatchSession, session_id)
    if not watch_session:
        raise HTTPException(status_code=404, detail="Session not found")
    return watch_session


def get_open_or_409(session: SessionDep, session_id: int) -> WatchSession:
    watch_session = get_or_404(session, session_id)
    if watch_session.picked_movie_id is not None:
        raise HTTPException(status_code=409, detail="This session already has a pick")
    return watch_session


@router.get("")
def list_sessions(session: SessionDep) -> list[WatchSession]:
    statement = (
        select(WatchSession).where(WatchSession.user_id == LOCAL_USER_ID).order_by(WatchSession.started_at.desc())
    )
    return list(session.exec(statement))


@router.post("", status_code=201)
def start_session(session: SessionDep) -> WatchSession:
    watch_session = WatchSession()
    session.add(watch_session)
    session.commit()
    session.refresh(watch_session)
    return watch_session


@router.get("/{session_id}")
def get_session_detail(session_id: int, session: SessionDep) -> SessionDetail:
    """The whole decision: shortlist, context answers, feedback and the final pick, kept together."""
    watch_session = get_or_404(session, session_id)
    candidates = session.exec(
        select(Movie)
        .join(SessionCandidate)
        .where(SessionCandidate.session_id == session_id)
        .order_by(SessionCandidate.added_at)
    )
    examples = session.exec(
        select(Movie, SessionExample.positive)
        .join(SessionExample)
        .where(SessionExample.session_id == session_id)
        .order_by(SessionExample.added_at)
    )
    signals = session.exec(select(Signal).where(Signal.session_id == session_id).order_by(Signal.created_at))
    return SessionDetail(
        session=watch_session,
        candidates=list(candidates),
        examples=[Example(movie=movie, positive=positive) for movie, positive in examples],
        signals=list(signals),
    )


@router.post("/{session_id}/candidates", status_code=201)
async def add_candidate(session_id: int, body: MovieRef, session: SessionDep) -> Movie:
    get_open_or_409(session, session_id)
    movie = await ensure_movie(session, body.movie_id)
    if not session.get(SessionCandidate, (session_id, movie.id)):
        session.add(SessionCandidate(session_id=session_id, movie_id=movie.id))
        session.add(Signal(kind=SignalKind.SHORTLISTED, movie_id=movie.id, session_id=session_id))
        session.commit()
    return movie


@router.delete("/{session_id}/candidates/{movie_id}", status_code=204)
def remove_candidate(session_id: int, movie_id: int, session: SessionDep) -> None:
    get_open_or_409(session, session_id)
    candidate = session.get(SessionCandidate, (session_id, movie_id))
    if not candidate:
        raise HTTPException(status_code=404, detail="Movie is not on this shortlist")
    session.delete(candidate)
    session.add(Signal(kind=SignalKind.UNSHORTLISTED, movie_id=movie_id, session_id=session_id))
    session.commit()


@router.put("/{session_id}/examples")
async def set_example(session_id: int, body: ExampleRef, session: SessionDep) -> Example:
    """Add a "like this" / "not this" example, or flip an existing one."""
    get_open_or_409(session, session_id)
    movie = await ensure_movie(session, body.movie_id)
    example = session.get(SessionExample, (session_id, movie.id))
    if not example or example.positive != body.positive:
        if example:
            example.positive = body.positive
        else:
            session.add(SessionExample(session_id=session_id, movie_id=movie.id, positive=body.positive))
        value = 1.0 if body.positive else -1.0
        session.add(Signal(kind=SignalKind.EXAMPLE_SET, movie_id=movie.id, value=value, session_id=session_id))
        session.commit()
    return Example(movie=movie, positive=body.positive)


@router.delete("/{session_id}/examples/{movie_id}", status_code=204)
def remove_example(session_id: int, movie_id: int, session: SessionDep) -> None:
    get_open_or_409(session, session_id)
    example = session.get(SessionExample, (session_id, movie_id))
    if not example:
        raise HTTPException(status_code=404, detail="Movie is not an example in this session")
    session.delete(example)
    session.add(Signal(kind=SignalKind.EXAMPLE_REMOVED, movie_id=movie_id, session_id=session_id))
    session.commit()


@router.post("/{session_id}/pick")
async def pick_movie(session_id: int, body: MovieRef, session: SessionDep) -> WatchSession:
    watch_session = get_open_or_409(session, session_id)
    movie = await ensure_movie(session, body.movie_id)
    watch_session.picked_movie_id = movie.id
    session.add(Signal(kind=SignalKind.PICKED, movie_id=movie.id, session_id=session_id))
    session.commit()
    session.refresh(watch_session)
    return watch_session
