import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import LOCAL_USER_ID
from app.db import SessionDep
from app.models import LibraryEntry, Movie, Signal, SignalKind, WatchSession
from app.services import brackets, library
from app.services.movies import ensure_movie
from app.services.ranking import bradley_terry

router = APIRouter(prefix="/games", tags=["games"])


class Comparison(BaseModel):
    """One matchup from a bracket or tier game. Answering it means both movies have been seen."""

    winner_id: int
    loser_id: int
    topic: str | None = None


class NameThree(BaseModel):
    """An answer to "Name 3 movies to ___". With a session_id it describes tonight's context."""

    prompt: str = Field(min_length=1)
    movie_ids: list[int] = Field(min_length=3, max_length=3)
    want: bool = True
    session_id: int | None = None


class NotSeen(BaseModel):
    movie_id: int
    topic: str | None = None


class BracketRequest(BaseModel):
    topic: str | None = None
    size: int = Field(default=8, ge=2, le=16, multiple_of=2)


class Bracket(BaseModel):
    pairs: list[tuple[Movie, Movie]]  # round one
    reserves: list[Movie]  # stand-ins for "haven't seen it"


class RankedMovie(BaseModel):
    movie: Movie
    strength: float  # Bradley-Terry log-odds; differences matter, not the absolute value
    sd: float  # how unsure the strength still is
    games: int


@router.post("/comparisons", status_code=201)
async def record_comparison(body: Comparison, session: SessionDep) -> Signal:
    if body.winner_id == body.loser_id:
        raise HTTPException(status_code=422, detail="A movie cannot be compared with itself")
    for movie_id in (body.winner_id, body.loser_id):
        library.set_status(session, await ensure_movie(session, movie_id), seen=True, change_intent=False)
    signal = Signal(
        kind=SignalKind.COMPARED,
        movie_id=body.winner_id,
        other_movie_id=body.loser_id,
        context={"topic": body.topic} if body.topic else {},
    )
    session.add(signal)
    session.commit()
    session.refresh(signal)
    return signal


def _comparisons(session: Session, topic: str | None) -> list[tuple[int, int]]:
    statement = select(Signal).where(Signal.user_id == LOCAL_USER_ID, Signal.kind == SignalKind.COMPARED)
    return [
        (signal.movie_id, signal.other_movie_id)
        for signal in session.exec(statement)
        if topic is None or signal.context.get("topic") == topic
    ]


@router.get("/rankings")
def rankings(session: SessionDep, topic: str | None = None) -> list[RankedMovie]:
    strengths = bradley_terry(_comparisons(session, topic))
    ranked = sorted(strengths.items(), key=lambda item: item[1].mean, reverse=True)
    return [
        RankedMovie(movie=session.get(Movie, movie_id), strength=round(s.mean, 3), sd=round(s.sd, 3), games=s.games)
        for movie_id, s in ranked
    ]


@router.post("/brackets")
async def start_bracket(body: BracketRequest, session: SessionDep) -> Bracket:
    entries = session.exec(select(LibraryEntry).where(LibraryEntry.user_id == LOCAL_USER_ID)).all()
    seen = [entry.movie_id for entry in entries if entry.seen]
    # Don't offer movies they've told us they haven't seen: on their list unseen, or skipped in a game.
    skipped = session.exec(select(Signal.movie_id).where(Signal.kind == SignalKind.NOT_SEEN)).all()
    not_seen = {entry.movie_id for entry in entries if not entry.seen} | (set(skipped) - set(seen))

    rng = random.Random()
    candidates = {movie.id: movie for movie in await brackets.well_known_movies(rng)}
    well_known = [movie_id for movie_id in candidates if movie_id not in not_seen]
    seeding = brackets.seed(seen, well_known, bradley_terry(_comparisons(session, body.topic)), body.size, rng)

    def movie(movie_id: int) -> Movie:
        return candidates.get(movie_id) or session.get(Movie, movie_id)

    if len(seeding.pairs) < body.size // 2:
        raise HTTPException(status_code=409, detail="Not enough movies for a bracket yet")
    return Bracket(
        pairs=[(movie(a), movie(b)) for a, b in seeding.pairs],
        reserves=[movie(movie_id) for movie_id in seeding.reserves],
    )


@router.post("/not-seen", status_code=201)
async def not_seen(body: NotSeen, session: SessionDep) -> Signal:
    """Answers "haven't seen it" in a game, so the same movie isn't offered again and again."""
    await ensure_movie(session, body.movie_id)
    signal = Signal(
        kind=SignalKind.NOT_SEEN, movie_id=body.movie_id, context={"topic": body.topic} if body.topic else {}
    )
    session.add(signal)
    session.commit()
    session.refresh(signal)
    return signal


@router.post("/name-three", status_code=201)
async def name_three(body: NameThree, session: SessionDep) -> list[Signal]:
    if body.session_id is not None and not session.get(WatchSession, body.session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    signals = []
    for movie_id in body.movie_ids:
        await ensure_movie(session, movie_id)
        signals.append(
            Signal(
                kind=SignalKind.NAMED,
                movie_id=movie_id,
                value=1.0 if body.want else -1.0,
                session_id=body.session_id,
                context={"prompt": body.prompt},
            )
        )
    session.add_all(signals)
    session.commit()
    for signal in signals:
        session.refresh(signal)
    return signals
