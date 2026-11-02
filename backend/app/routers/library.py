from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.config import LOCAL_USER_ID
from app.db import SessionDep
from app.models import Intent, LibraryEntry, Movie, Signal, SignalKind, now
from app.services.movies import ensure_movie

router = APIRouter(prefix="/library", tags=["library"])


class LibraryUpdate(BaseModel):
    """Partial update: only the fields sent are changed. Send intent=null to clear it."""

    seen: bool | None = None
    intent: Intent | None = None


class LibraryItem(BaseModel):
    movie: Movie
    seen: bool
    intent: Intent | None
    updated_at: datetime


@router.get("")
def get_library(session: SessionDep) -> list[LibraryItem]:
    statement = (
        select(LibraryEntry, Movie)
        .join(Movie)
        .where(LibraryEntry.user_id == LOCAL_USER_ID)
        .order_by(LibraryEntry.updated_at.desc())
    )
    return [
        LibraryItem(movie=movie, seen=entry.seen, intent=entry.intent, updated_at=entry.updated_at)
        for entry, movie in session.exec(statement)
    ]


@router.patch("/{movie_id}")
async def update_entry(movie_id: int, body: LibraryUpdate, session: SessionDep) -> LibraryItem:
    movie = await ensure_movie(session, movie_id)
    entry = session.get(LibraryEntry, (LOCAL_USER_ID, movie.id)) or LibraryEntry(movie_id=movie.id)
    previous = {"seen": entry.seen, "intent": entry.intent}

    seen = entry.seen if body.seen is None else body.seen
    intent = body.intent if "intent" in body.model_fields_set else entry.intent
    if seen and not entry.seen and "intent" not in body.model_fields_set:
        intent = None  # watching it fulfils the old Want / Curious
    if seen and intent == Intent.CURIOUS:
        raise HTTPException(status_code=422, detail="A seen movie can be wanted again (rewatch), not curious")

    if {"seen": seen, "intent": intent} != previous:
        entry.seen, entry.intent, entry.updated_at = seen, intent, now()
        if seen or intent:
            session.add(entry)
            session.add(
                Signal(
                    kind=SignalKind.STATUS_SET,
                    movie_id=movie.id,
                    context={"seen": seen, "intent": intent, "previous": previous},
                )
            )
        else:
            _clear(session, entry, previous)
        session.commit()
    return LibraryItem(movie=movie, seen=entry.seen, intent=entry.intent, updated_at=entry.updated_at)


@router.delete("/{movie_id}", status_code=204)
def clear_entry(movie_id: int, session: SessionDep) -> None:
    entry = session.get(LibraryEntry, (LOCAL_USER_ID, movie_id))
    if not entry:
        raise HTTPException(status_code=404, detail="Movie is not in your library")
    _clear(session, entry, {"seen": entry.seen, "intent": entry.intent})
    session.commit()


def _clear(session: SessionDep, entry: LibraryEntry, previous: dict) -> None:
    session.delete(entry)
    # Removal is information too, e.g. a Curious movie that turned out irrelevant.
    session.add(Signal(kind=SignalKind.STATUS_CLEARED, movie_id=entry.movie_id, context={"previous": previous}))
