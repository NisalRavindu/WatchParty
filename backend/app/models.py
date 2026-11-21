from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import JSON, Column, Field, SQLModel

from app.config import LOCAL_USER_ID


def now() -> datetime:
    return datetime.now(UTC)


class Movie(SQLModel, table=True):
    """Local cache of TMDB movie details. The id is the TMDB id."""

    id: int = Field(primary_key=True)
    title: str
    release_date: str | None = None
    poster_path: str | None = None
    overview: str = ""
    genres: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Intent(StrEnum):
    WANT = "want"  # want to watch; on a seen movie this means rewatch
    CURIOUS = "curious"  # "maybe" - keeps Want free of movies that turn out irrelevant


class LibraryEntry(SQLModel, table=True):
    """The user's relationship with a movie: whether they've seen it, and what they intend.

    Seen + Want is a rewatch. A seen movie can't be Curious.
    """

    user_id: int = Field(default=LOCAL_USER_ID, primary_key=True)
    movie_id: int = Field(foreign_key="movie.id", primary_key=True)
    seen: bool = False
    intent: Intent | None = None
    updated_at: datetime = Field(default_factory=now)


class WatchSession(SQLModel, table=True):
    """One "what do we watch now?" decision, from context to final pick."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = LOCAL_USER_ID
    started_at: datetime = Field(default_factory=now)
    picked_movie_id: int | None = Field(default=None, foreign_key="movie.id")


class SessionCandidate(SQLModel, table=True):
    """A movie on a session's shortlist."""

    session_id: int = Field(foreign_key="watchsession.id", primary_key=True)
    movie_id: int = Field(foreign_key="movie.id", primary_key=True)
    added_at: datetime = Field(default_factory=now)


class SessionExample(SQLModel, table=True):
    """A movie that says what tonight is (positive) or isn't (negative) about. Context, not a candidate."""

    session_id: int = Field(foreign_key="watchsession.id", primary_key=True)
    movie_id: int = Field(foreign_key="movie.id", primary_key=True)
    positive: bool
    added_at: datetime = Field(default_factory=now)


class SignalKind(StrEnum):
    COMPARED = "compared"  # movie_id beat other_movie_id (brackets, tier games)
    NAMED = "named"  # answered a "Name 3 movies to ___" prompt; value +1 want / -1 don't want
    SHORTLISTED = "shortlisted"  # put on a session's shortlist
    UNSHORTLISTED = "unshortlisted"  # taken off the shortlist without being picked
    PICKED = "picked"  # final pick of a session
    STATUS_SET = "status_set"  # library entry changed (context: seen, intent, previous)
    STATUS_CLEARED = "status_cleared"  # removed from the library (context.previous)
    EXAMPLE_SET = "example_set"  # session example added or flipped; value +1 like this / -1 not this
    EXAMPLE_REMOVED = "example_removed"  # session example taken back


class Signal(SQLModel, table=True):
    """Every preference input is logged here. Rankings, heat and suggestions are derived from it."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = LOCAL_USER_ID
    kind: SignalKind
    movie_id: int = Field(foreign_key="movie.id")
    other_movie_id: int | None = Field(default=None, foreign_key="movie.id")
    value: float = 1.0
    session_id: int | None = Field(default=None, foreign_key="watchsession.id")
    context: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
