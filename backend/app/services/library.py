from sqlmodel import Session

from app.config import LOCAL_USER_ID
from app.models import Intent, LibraryEntry, Movie, Signal, SignalKind, now


class StatusError(ValueError):
    """A status combination that doesn't make sense."""


def set_status(
    session: Session, movie: Movie, seen: bool | None = None, intent: Intent | None = None, *, change_intent: bool
) -> LibraryEntry:
    """Change what the user has seen / intends for a movie, logging the change. Doesn't commit.

    seen=None keeps it as it is; the intent only changes when change_intent is true.
    """
    entry = session.get(LibraryEntry, (LOCAL_USER_ID, movie.id)) or LibraryEntry(movie_id=movie.id)
    previous = {"seen": entry.seen, "intent": entry.intent}

    new_seen = entry.seen if seen is None else seen
    new_intent = intent if change_intent else entry.intent
    if new_seen and not entry.seen and not change_intent:
        new_intent = None  # watching it fulfils the old Want / Curious
    if new_seen and new_intent == Intent.CURIOUS:
        raise StatusError("A seen movie can be wanted again (rewatch), not curious")

    if {"seen": new_seen, "intent": new_intent} != previous:
        entry.seen, entry.intent, entry.updated_at = new_seen, new_intent, now()
        if new_seen or new_intent:
            session.add(entry)
            session.add(
                Signal(
                    kind=SignalKind.STATUS_SET,
                    movie_id=movie.id,
                    context={"seen": new_seen, "intent": new_intent, "previous": previous},
                )
            )
        else:
            clear(session, entry, previous)
    return entry


def clear(session: Session, entry: LibraryEntry, previous: dict | None = None) -> None:
    previous = previous or {"seen": entry.seen, "intent": entry.intent}
    session.delete(entry)
    # Removal is information too, e.g. a Curious movie that turned out irrelevant.
    session.add(Signal(kind=SignalKind.STATUS_CLEARED, movie_id=entry.movie_id, context={"previous": previous}))
