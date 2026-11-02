import asyncio
from datetime import date

from app.services import search as search_service
from app.services import studios, tmdb
from app.services.search import SearchBy, SearchFilters
from app.services.text import singular_plural, split_exclusions, split_terms


def test_split_terms():
    assert split_terms("disney + pixar") == ["disney", "pixar"]
    assert split_terms(" A24, ghibli ,") == ["A24", "ghibli"]
    assert split_terms("alien + small town -horror") == ["alien", "small town", "-horror"]
    assert split_terms("sci-fi, -x-men") == ["sci-fi", "-x-men"]  # hyphens inside words stay


def test_split_exclusions():
    assert split_exclusions(["alien", "-horror", "- monster", "-"]) == (["alien"], ["horror", "monster"])


def test_singular_plural():
    assert singular_plural("Alien") == {"alien", "aliens"}
    assert singular_plural("dreams") == {"dreams", "dream"}


def test_known_brands_resolve_without_tmdb(monkeypatch):
    async def fail(query):
        raise AssertionError("known studios should not hit TMDB search")

    monkeypatch.setattr(tmdb, "search_companies", fail)
    ids, names = asyncio.run(studios.resolve(["Disney", "Pixar"]))
    assert ids == [2, 6125, 3]
    assert names == ["Walt Disney Pictures", "Walt Disney Animation Studios", "Pixar"]

    # Punctuation and repeats don't matter.
    assert asyncio.run(studios.resolve(["Warner Bros.", "warner"]))[0] == [174]


def test_unknown_studio_prefers_exact_then_prefix_matches(monkeypatch):
    async def search_companies(query):
        return [
            {"id": 1, "name": "Neon Rated Films"},
            {"id": 2, "name": "NEON"},
            {"id": 3, "name": "Neon Productions"},
        ]

    monkeypatch.setattr(tmdb, "search_companies", search_companies)
    assert asyncio.run(studios.resolve(["neon"])) == ([2, 3], ["NEON", "Neon Productions"])
    assert asyncio.run(studios.resolve(["neon r"])) == ([1], ["Neon Rated Films"])


def test_generic_words_do_not_block_a_match(monkeypatch):
    async def search_companies(query):
        return [
            {"id": 1, "name": "Studio Outrigger"},
            {"id": 2, "name": "TRIGGER"},
            {"id": 3, "name": "Trigger Happy Studios"},
        ]

    monkeypatch.setattr(tmdb, "search_companies", search_companies)
    assert asyncio.run(studios.resolve(["studio trigger"])) == ([2], ["TRIGGER"])


def test_studio_search_combines_companies_as_either(monkeypatch):
    sent = {}

    async def discover_movies(first_page, page_count, **params):
        sent.update(params)
        return {"results": [], "total_pages": 0, "total_results": 0}

    async def genre_names():
        return {}

    monkeypatch.setattr(tmdb, "discover_movies", discover_movies)
    monkeypatch.setattr(search_service, "genre_names", genre_names)

    filters = SearchFilters(q="disney + pixar", by=SearchBy.STUDIO, genre=35)
    result = asyncio.run(search_service.search(filters, date(2026, 11, 1)))
    assert result.matched == "Studios: Walt Disney Pictures, Walt Disney Animation Studios, Pixar"
    assert sent["with_companies"] == "2|6125|3"
    assert sent["with_genres"] == "35"

    sent.clear()
    filters = SearchFilters(q="dreamworks -dreamworks animation", by=SearchBy.STUDIO)
    result = asyncio.run(search_service.search(filters, date(2026, 11, 1)))
    assert result.matched == "Studios: DreamWorks Animation, DreamWorks Pictures · without DreamWorks Animation"
    assert (sent["with_companies"], sent["without_companies"]) == ("521|7", "521")
