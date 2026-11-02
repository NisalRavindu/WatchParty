import asyncio
import math
import re
from datetime import date
from enum import StrEnum
from typing import NamedTuple

from pydantic import BaseModel, Field

from app.services import studios, tmdb
from app.services.text import singular_plural, split_exclusions, split_terms

# One page of our results is this many TMDB pages (20 movies each).
TMDB_PAGES_PER_PAGE = 3
PAGE_SIZE = 20 * TMDB_PAGES_PER_PAGE
MAX_PAGE = math.ceil(tmdb.MAX_PAGE / TMDB_PAGES_PER_PAGE)
# Below this many votes an entry is usually a placeholder, student film or extra.
MIN_VOTES = 5
# Top-rated sorting only trusts averages backed by this many votes.
RATING_MIN_VOTES = 50
# Cast credits like "Self (archive footage)" are appearances in documentaries, not roles.
SELF_APPEARANCE = re.compile(r"^(self|himself|herself|themselves)\b", re.IGNORECASE)


class SearchBy(StrEnum):
    TITLE = "title"
    PERSON = "person"
    KEYWORD = "keyword"
    STUDIO = "studio"


class Role(StrEnum):
    AUTO = "auto"  # what the person is known for
    ANY = "any"
    ACTING = "acting"
    DIRECTING = "directing"


class Match(StrEnum):
    """How several keywords combine."""

    ALL = "all"
    ANY = "any"


class SortBy(StrEnum):
    RELEVANCE = "relevance"
    NEWEST = "newest"
    OLDEST = "oldest"
    RATING = "rating"
    TITLE = "title"


class SearchFilters(BaseModel):
    q: str = Field(min_length=1)
    by: SearchBy = SearchBy.TITLE
    role: Role = Role.AUTO
    match: Match = Match.ALL  # keyword search: "alien + small town" needs both, or either
    genre: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    language: str | None = None  # ISO 639-1, e.g. "en", "ja"
    sort: SortBy = SortBy.RELEVANCE
    include_obscure: bool = False  # video extras, entries with no genres or almost no votes
    include_upcoming: bool = False
    page: int = Field(default=1, ge=1, le=MAX_PAGE)


class MovieResult(BaseModel):
    id: int
    title: str
    release_date: str | None
    poster_path: str | None
    original_language: str | None
    vote_average: float
    vote_count: int
    genres: list[str]
    credit: str | None = None  # "as Dom Cobb" / "Director" when searching by person


class SearchResults(BaseModel):
    matched: str | None  # what the query resolved to, e.g. "Christopher Nolan · directing"
    results: list[MovieResult]
    page: int
    total_pages: int
    total_results: int
    total_is_estimate: bool  # TMDB's count before our filters drop extras and placeholders


class Found(NamedTuple):
    """What one search mode found: either one TMDB-paged page, or the complete list to page here."""

    matched: str | None
    movies: list[dict]
    tmdb: dict | None = None  # TMDB paging info ({"total_pages", "total_results"}); None = complete list


_genre_names: dict[int, str] = {}


async def genre_names() -> dict[int, str]:
    if not _genre_names:
        _genre_names.update({genre["id"]: genre["name"] for genre in await tmdb.movie_genres()})
    return _genre_names


# ---- Filtering and sorting (pure) ----


def is_real_movie(movie: dict) -> bool:
    return not movie.get("video") and bool(movie.get("genre_ids")) and movie.get("vote_count", 0) >= MIN_VOTES


def is_released(movie: dict, today: date) -> bool:
    release_date = movie.get("release_date")
    return bool(release_date) and release_date <= today.isoformat()


def matches(movie: dict, filters: SearchFilters, today: date) -> bool:
    year = int(movie["release_date"][:4]) if movie.get("release_date") else None
    return (
        (filters.include_obscure or is_real_movie(movie))
        and (filters.include_upcoming or is_released(movie, today))
        and (filters.genre is None or filters.genre in movie.get("genre_ids", []))
        and (filters.year_from is None or (year is not None and year >= filters.year_from))
        and (filters.year_to is None or (year is not None and year <= filters.year_to))
        and (filters.language is None or movie.get("original_language") == filters.language)
    )


def sort_movies(movies: list[dict], sort: SortBy) -> list[dict]:
    if sort == SortBy.NEWEST:
        return sorted(movies, key=lambda m: m.get("release_date") or "", reverse=True)
    if sort == SortBy.OLDEST:
        return sorted(movies, key=lambda m: m.get("release_date") or "9999")
    if sort == SortBy.RATING:
        return sorted(
            movies,
            key=lambda m: (m.get("vote_count", 0) >= RATING_MIN_VOTES, m.get("vote_average", 0)),
            reverse=True,
        )
    if sort == SortBy.TITLE:
        return sorted(movies, key=lambda m: m["title"].casefold())
    return movies  # relevance: keep the source order


def dedupe(movies: list[dict]) -> list[dict]:
    seen: set[int] = set()
    return [movie for movie in movies if not (movie["id"] in seen or seen.add(movie["id"]))]


# ---- Finding candidates ----


def _first_tmdb_page(filters: SearchFilters) -> int:
    return (filters.page - 1) * TMDB_PAGES_PER_PAGE + 1


async def _by_title(filters: SearchFilters) -> Found:
    data = await tmdb.search_movies(filters.q, _first_tmdb_page(filters), TMDB_PAGES_PER_PAGE)
    return Found(None, data["results"], data)


async def _by_person(filters: SearchFilters) -> Found:
    people = await tmdb.search_people(filters.q)
    if not people:
        return Found(f'No one found for "{filters.q}"', [])
    person = people[0]

    role = filters.role
    if role == Role.AUTO:
        role = {"Acting": Role.ACTING, "Directing": Role.DIRECTING}.get(person.get("known_for_department"), Role.ANY)

    credits = await tmdb.person_movie_credits(person["id"])
    cast = [
        {**movie, "credit": f"as {movie['character']}" if movie.get("character") else None}
        for movie in credits["cast"]
        if filters.include_obscure or not SELF_APPEARANCE.match(movie.get("character") or "")
    ]
    crew = [{**movie, "credit": movie.get("job")} for movie in credits["crew"]]
    movies = {
        Role.ACTING: cast,
        Role.DIRECTING: [movie for movie in crew if movie.get("job") == "Director"],
        Role.ANY: cast + crew,
    }[role]

    movies = sorted(dedupe(movies), key=lambda m: m.get("popularity", 0), reverse=True)
    return Found(f"{person['name']} · {role}", movies)  # the whole filmography; paged in search()


DISCOVER_SORT = {
    SortBy.RELEVANCE: "popularity.desc",
    SortBy.NEWEST: "primary_release_date.desc",
    SortBy.OLDEST: "primary_release_date.asc",
    SortBy.RATING: "vote_average.desc",
    SortBy.TITLE: "title.asc",
}


async def _discover(filters: SearchFilters, today: date, genres: tuple[int, ...] = (), **params) -> dict:
    """Discover filters on TMDB's side, so results aren't limited to the most popular few pages."""
    params["sort_by"] = DISCOVER_SORT[filters.sort]
    all_genres = [*genres, *([filters.genre] if filters.genre is not None else [])]
    if all_genres:
        params["with_genres"] = ",".join(str(genre) for genre in dict.fromkeys(all_genres))
    if filters.language:
        params["with_original_language"] = filters.language
    if filters.year_from is not None:
        params["primary_release_date.gte"] = f"{filters.year_from}-01-01"
    latest = [f"{filters.year_to}-12-31"] if filters.year_to is not None else []
    if not filters.include_upcoming:
        latest.append(today.isoformat())
    if latest:
        params["primary_release_date.lte"] = min(latest)
    min_votes = RATING_MIN_VOTES if filters.sort == SortBy.RATING else 0 if filters.include_obscure else MIN_VOTES
    if min_votes:
        params["vote_count.gte"] = min_votes
    return await tmdb.discover_movies(_first_tmdb_page(filters), TMDB_PAGES_PER_PAGE, **params)


async def _keywords_for(term: str) -> list[dict]:
    """TMDB keywords for one term, best first. TMDB keeps "alien" and "aliens" apart, so take both."""
    keywords = await tmdb.search_keywords(term)
    forms = singular_plural(term)
    exact = [keyword for keyword in keywords if keyword["name"].casefold() in forms]
    exact.sort(key=lambda keyword: keyword["name"].casefold() != term.casefold())  # the form typed first
    return exact or keywords[:3]


def _ids(items: list[dict], separator: str = "|") -> str:
    return separator.join(str(item["id"]) for item in items)


async def _by_keyword(filters: SearchFilters, today: date) -> Found:
    wanted, unwanted = split_exclusions(split_terms(filters.q))
    if not wanted and not unwanted:
        return Found("Type a keyword, e.g. heist", [])

    # Genre words ("heist + comedy", "-horror") are rarely keyword tags on TMDB, so they act on the
    # genre instead. A wanted genre only works with "all": TMDB can't OR a genre with a keyword.
    genres = {name.casefold(): {"id": genre_id, "name": name} for genre_id, name in (await genre_names()).items()}
    with_genres = [genres[term.casefold()] for term in wanted if filters.match == Match.ALL and term.casefold() in genres]
    without_genres = [genres[term.casefold()] for term in unwanted if term.casefold() in genres]
    wanted = [term for term in wanted if not (filters.match == Match.ALL and term.casefold() in genres)]
    unwanted = [term for term in unwanted if term.casefold() not in genres]

    groups = await asyncio.gather(*(_keywords_for(term) for term in wanted + unwanted))
    if missing := [term for term, group in zip(wanted + unwanted, groups) if not group]:
        return Found(f'No keyword matches "{missing[0]}"', [])
    wanted_groups, unwanted_groups = groups[: len(wanted)], groups[len(wanted) :]

    # TMDB can't mix "," (all) and "|" (any) reliably, so "all" uses each term's best keyword
    # while "any" can take every form.
    if filters.match == Match.ALL:
        wanted_groups = [group[:1] for group in wanted_groups]
    params: dict = {}
    if wanted_groups:
        params["with_keywords"] = _ids([k for group in wanted_groups for k in group], "," if filters.match == Match.ALL else "|")
    if unwanted_groups:
        params["without_keywords"] = _ids([k for group in unwanted_groups for k in group])  # drops movies with any
    if without_genres:
        params["without_genres"] = _ids(without_genres)

    if wanted_groups:
        names = [" / ".join(k["name"] for k in group) for group in wanted_groups]
        names += [f"{genre['name']} (genre)" for genre in with_genres]
        joiner = " + " if filters.match == Match.ALL else " or "
        label = ("Keywords: " if len(wanted_groups) > 1 else "Keyword: ") + joiner.join(names)
    elif with_genres:
        label = ("Genres: " if len(with_genres) > 1 else "Genre: ") + " + ".join(genre["name"] for genre in with_genres)
    else:
        label = "All movies"
    excluded = [" / ".join(k["name"] for k in group) for group in unwanted_groups]
    excluded += [f"{genre['name']} (genre)" for genre in without_genres]
    if excluded:
        label += " · without " + ", ".join(excluded)

    data = await _discover(filters, today, genres=tuple(genre["id"] for genre in with_genres), **params)
    return Found(label, data["results"], data)


async def _by_studio(filters: SearchFilters, today: date) -> Found:
    wanted, unwanted = split_exclusions(split_terms(filters.q))
    (ids, names), (excluded_ids, excluded_names) = await asyncio.gather(studios.resolve(wanted), studios.resolve(unwanted))
    if not ids:
        return Found(f'No studio matches "{filters.q}"', [])

    # "|" = from any of these companies. "," (all of them) would miss most films; Pixar's
    # are usually credited to Pixar alone, so "disney + pixar" means either.
    label = ("Studios: " if len(names) > 1 else "Studio: ") + ", ".join(names)
    params = {"with_companies": "|".join(str(company_id) for company_id in ids)}
    if excluded_ids:
        label += " · without " + ", ".join(excluded_names)
        params["without_companies"] = "|".join(str(company_id) for company_id in excluded_ids)
    data = await _discover(filters, today, **params)
    return Found(label, data["results"], data)


async def search(filters: SearchFilters, today: date | None = None) -> SearchResults:
    today = today or date.today()
    if filters.by == SearchBy.PERSON:
        found = await _by_person(filters)
    elif filters.by == SearchBy.KEYWORD:
        found = await _by_keyword(filters, today)
    elif filters.by == SearchBy.STUDIO:
        found = await _by_studio(filters, today)
    else:
        found = await _by_title(filters)

    movies = sort_movies([movie for movie in found.movies if matches(movie, filters, today)], filters.sort)
    if found.tmdb is None:
        # The complete list: count it exactly and cut out the requested page here.
        total_results, is_estimate = len(movies), False
        total_pages = math.ceil(total_results / PAGE_SIZE)
        movies = movies[(filters.page - 1) * PAGE_SIZE : filters.page * PAGE_SIZE]
    else:
        tmdb_pages = min(found.tmdb["total_pages"], tmdb.MAX_PAGE)
        total_pages = math.ceil(tmdb_pages / TMDB_PAGES_PER_PAGE)
        total_results, is_estimate = found.tmdb["total_results"], True
        if total_pages <= 1:
            total_results, is_estimate = len(movies), False

    names = await genre_names()
    return SearchResults(
        matched=found.matched,
        page=filters.page,
        total_pages=max(total_pages, 1),
        total_results=total_results,
        total_is_estimate=is_estimate,
        results=[
            MovieResult(
                id=movie["id"],
                title=movie["title"],
                release_date=movie.get("release_date") or None,
                poster_path=movie.get("poster_path"),
                original_language=movie.get("original_language"),
                vote_average=movie.get("vote_average", 0),
                vote_count=movie.get("vote_count", 0),
                genres=[names[genre_id] for genre_id in movie.get("genre_ids", []) if genre_id in names],
                credit=movie.get("credit"),
            )
            for movie in movies
        ],
    )
