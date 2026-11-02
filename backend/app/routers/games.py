from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.config import LOCAL_USER_ID
from app.db import SessionDep
from app.models import Movie, Signal, SignalKind, WatchSession
from app.services.movies import ensure_movie
from app.services.ranking import elo_ratings

router = APIRouter(prefix="/games", tags=["games"])


class Comparison(BaseModel):
    """One matchup from a bracket or tier game."""

    winner_id: int
    loser_id: int
    topic: str | None = None


class NameThree(BaseModel):
    """An answer to "Name 3 movies to ___". With a session_id it describes tonight's context."""

    prompt: str = Field(min_length=1)
    movie_ids: list[int] = Field(min_length=3, max_length=3)
    want: bool = True
    session_id: int | None = None


class RankedMovie(BaseModel):
    movie: Movie
    rating: float


@router.post("/comparisons", status_code=201)
async def record_comparison(body: Comparison, session: SessionDep) -> Signal:
    if body.winner_id == body.loser_id:
        raise HTTPException(status_code=422, detail="A movie cannot be compared with itself")
    await ensure_movie(session, body.winner_id)
    await ensure_movie(session, body.loser_id)
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


@router.get("/rankings")
def rankings(session: SessionDep, topic: str | None = None) -> list[RankedMovie]:
    statement = (
        select(Signal)
        .where(Signal.user_id == LOCAL_USER_ID, Signal.kind == SignalKind.COMPARED)
        .order_by(Signal.created_at)
    )
    comparisons = [
        (signal.movie_id, signal.other_movie_id)
        for signal in session.exec(statement)
        if topic is None or signal.context.get("topic") == topic
    ]
    ratings = elo_ratings(comparisons)
    ranked = sorted(ratings.items(), key=lambda item: item[1], reverse=True)
    return [RankedMovie(movie=session.get(Movie, movie_id), rating=round(rating, 1)) for movie_id, rating in ranked]


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
