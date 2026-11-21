from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.config import LOCAL_USER_ID
from app.db import SessionDep
from app.models import Intent, LibraryEntry, Movie
from app.services import library
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
    try:
        entry = library.set_status(
            session, movie, body.seen, body.intent, change_intent="intent" in body.model_fields_set
        )
    except library.StatusError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return LibraryItem(movie=movie, seen=entry.seen, intent=entry.intent, updated_at=entry.updated_at)


@router.delete("/{movie_id}", status_code=204)
def clear_entry(movie_id: int, session: SessionDep) -> None:
    entry = session.get(LibraryEntry, (LOCAL_USER_ID, movie_id))
    if not entry:
        raise HTTPException(status_code=404, detail="Movie is not in your library")
    library.clear(session, entry)
    session.commit()
