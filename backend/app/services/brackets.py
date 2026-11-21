"""Seeding brackets: which movies play, and who meets whom in round one.

Half the field comes from movies the user has already seen, the least settled first, so each bracket
sharpens the rankings. The rest are well-known movies they may have seen: playing them is how Seen
fills up without a chore. Spare well-known movies stand by for "haven't seen it".
"""

import random
from datetime import date
from typing import NamedTuple

from app.models import Movie
from app.services import tmdb
from app.services.ranking import Strength, most_informative_pairs, unrated
from app.services.search import genre_names, is_real_movie, is_released

# Pages of TMDB's most-voted movies to draw well-known movies from (20 per page).
WELL_KNOWN_PAGES = 15


class Seeding(NamedTuple):
    pairs: list[tuple[int, int]]
    reserves: list[int]


def seed(
    seen: list[int], well_known: list[int], strengths: dict[int, Strength], size: int, rng: random.Random
) -> Seeding:
    """Pick `size` movies (even) and pair them up for round one. Pure, so it can be tested."""
    known = sorted(seen, key=lambda movie: (-strengths.get(movie, unrated()).sd, rng.random()))
    fresh = [movie for movie in well_known if movie not in set(seen)]
    rng.shuffle(fresh)

    chosen = known[: size // 2]
    chosen += fresh[: size - len(chosen)]
    chosen += known[size // 2 : size // 2 + size - len(chosen)]  # not enough fresh: more of the seen ones
    chosen = chosen[: len(chosen) // 2 * 2]
    reserves = [movie for movie in fresh if movie not in chosen]
    pairs = most_informative_pairs({movie: strengths.get(movie, unrated()) for movie in chosen})
    rng.shuffle(pairs)  # informative pairs, but not always the same order
    return Seeding(pairs, reserves)


async def well_known_movies(rng: random.Random, today: date | None = None) -> list[Movie]:
    """One random page of TMDB's most-voted movies, as unsaved Movie objects."""
    today = today or date.today()
    page = rng.randint(1, WELL_KNOWN_PAGES)
    data = await tmdb.discover_movies(first_page=page, page_count=1, sort_by="vote_count.desc")
    names = await genre_names()
    return [
        Movie(
            id=movie["id"],
            title=movie["title"],
            release_date=movie.get("release_date") or None,
            poster_path=movie.get("poster_path"),
            overview=movie.get("overview") or "",
            genres=[names[genre] for genre in movie.get("genre_ids", []) if genre in names],
        )
        for movie in data["results"]
        if is_real_movie(movie) and is_released(movie, today)
    ]
