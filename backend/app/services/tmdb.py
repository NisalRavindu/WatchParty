import asyncio

import httpx

from app.config import TMDB_API_KEY, TMDB_BASE_URL


async def _get(path: str, **params) -> dict:
    if not TMDB_API_KEY:
        raise RuntimeError("TMDB_API_KEY is missing from the .env file")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{TMDB_BASE_URL}{path}",
            params={"api_key": TMDB_API_KEY, **params},
        )
        response.raise_for_status()
        return response.json()


MAX_PAGE = 500  # TMDB refuses pages beyond this


async def _get_pages(path: str, first_page: int, page_count: int, **params) -> dict:
    """Fetch page_count consecutive pages of a paged endpoint, starting at first_page.

    Returns {"results": [...], "total_pages": n, "total_results": n} like a single page would.
    """
    first = await _get(path, page=first_page, **params)
    last_page = min(first.get("total_pages", 1), first_page + page_count - 1, MAX_PAGE)
    rest = await asyncio.gather(*(_get(path, page=page, **params) for page in range(first_page + 1, last_page + 1)))
    return {
        "results": [result for page in (first, *rest) for result in page["results"]],
        "total_pages": first.get("total_pages", 1),
        "total_results": first.get("total_results", 0),
    }


async def search_movies(query: str, first_page: int = 1, page_count: int = 3) -> dict:
    return await _get_pages("/search/movie", first_page, page_count, query=query, include_adult=False)


async def search_people(query: str) -> list[dict]:
    return (await _get("/search/person", query=query, include_adult=False))["results"]


async def search_keywords(query: str) -> list[dict]:
    return (await _get("/search/keyword", query=query))["results"]


async def search_companies(query: str) -> list[dict]:
    return (await _get_pages("/search/company", 1, 2, query=query))["results"]


async def person_movie_credits(person_id: int) -> dict:
    return await _get(f"/person/{person_id}/movie_credits")


async def discover_movies(first_page: int = 1, page_count: int = 3, **params) -> dict:
    return await _get_pages(
        "/discover/movie", first_page, page_count, include_adult=False, include_video=False, **params
    )


async def movie_genres() -> list[dict]:
    return (await _get("/genre/movie/list"))["genres"]


async def get_movie(movie_id: int) -> dict:
    return await _get(f"/movie/{movie_id}")
