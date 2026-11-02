from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.search import SearchFilters, SearchResults, genre_names, search

router = APIRouter(prefix="/movies", tags=["movies"])


class Genre(BaseModel):
    id: int
    name: str


@router.get("/search")
async def movie_search(filters: Annotated[SearchFilters, Query()]) -> SearchResults:
    return await search(filters)


@router.get("/genres")
async def genres() -> list[Genre]:
    names = await genre_names()
    return [Genre(id=genre_id, name=name) for genre_id, name in sorted(names.items(), key=lambda item: item[1])]
