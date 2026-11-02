import httpx
from sqlmodel import Session

from app.models import Movie
from app.services import tmdb


async def ensure_movie(session: Session, movie_id: int) -> Movie:
    """Return the cached movie, fetching it from TMDB the first time it is referenced."""
    movie = session.get(Movie, movie_id)
    if movie:
        return movie

    try:
        data = await tmdb.get_movie(movie_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise LookupError(f"Movie {movie_id} not found on TMDB") from exc
        raise

    movie = Movie(
        id=data["id"],
        title=data["title"],
        release_date=data.get("release_date") or None,
        poster_path=data.get("poster_path"),
        overview=data.get("overview") or "",
        genres=[genre["name"] for genre in data.get("genres", [])],
    )
    session.add(movie)
    session.commit()
    return movie
