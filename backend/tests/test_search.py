import asyncio
from datetime import date

from app.services import search as search_service
from app.services import tmdb
from app.services.search import SearchBy, SearchFilters, SortBy, matches, sort_movies

TODAY = date(2026, 11, 1)


def movie(id, title="Movie", release_date="2010-01-01", genre_ids=(18,), vote_count=100, **extra):
    return {
        "id": id,
        "title": title,
        "release_date": release_date,
        "genre_ids": list(genre_ids),
        "vote_count": vote_count,
        "vote_average": 7.0,
        "video": False,
        "original_language": "en",
        **extra,
    }


def test_hides_extras_placeholders_and_unreleased_by_default():
    filters = SearchFilters(q="x")
    assert matches(movie(1), filters, TODAY)
    assert not matches(movie(2, video=True), filters, TODAY)
    assert not matches(movie(3, genre_ids=()), filters, TODAY)
    assert not matches(movie(4, vote_count=0), filters, TODAY)
    assert not matches(movie(5, release_date=""), filters, TODAY)
    assert not matches(movie(6, release_date="2027-05-01"), filters, TODAY)

    everything = SearchFilters(q="x", include_obscure=True, include_upcoming=True)
    assert all(matches(m, everything, TODAY) for m in [movie(2, video=True), movie(5, release_date="")])


def test_genre_year_and_language_filters():
    filters = SearchFilters(q="x", genre=18, year_from=2000, year_to=2015, language="en")
    assert matches(movie(1), filters, TODAY)
    assert not matches(movie(2, genre_ids=(35,)), filters, TODAY)
    assert not matches(movie(3, release_date="1999-12-31"), filters, TODAY)
    assert not matches(movie(4, original_language="ja"), filters, TODAY)


def test_rating_sort_puts_well_voted_movies_first():
    lucky = movie(1, vote_count=6, vote_average=10.0)
    solid = movie(2, vote_count=5000, vote_average=8.0)
    assert [m["id"] for m in sort_movies([lucky, solid], SortBy.RATING)] == [2, 1]


async def no_genres():
    return {}


def test_tmdb_paged_modes_fetch_the_matching_block_of_tmdb_pages(monkeypatch):
    calls = []

    async def search_movies(query, first_page, page_count):
        calls.append((first_page, page_count))
        return {"results": [movie(1)], "total_pages": 25, "total_results": 490}

    monkeypatch.setattr(tmdb, "search_movies", search_movies)
    monkeypatch.setattr(search_service, "genre_names", no_genres)

    result = asyncio.run(search_service.search(SearchFilters(q="love", page=3), TODAY))
    assert calls == [(7, 3)]  # our page 3 = TMDB pages 7-9
    assert (result.page, result.total_pages, result.total_results, result.total_is_estimate) == (3, 9, 490, True)


def test_complete_lists_are_paged_here_with_exact_counts(monkeypatch):
    async def search_people(query):
        return [{"id": 1, "name": "Busy Actor", "known_for_department": "Acting"}]

    async def person_movie_credits(person_id):
        cast = [movie(i, title=f"Film {i}", character="Lead", popularity=1000 - i) for i in range(130)]
        return {"cast": cast, "crew": []}

    monkeypatch.setattr(tmdb, "search_people", search_people)
    monkeypatch.setattr(tmdb, "person_movie_credits", person_movie_credits)
    monkeypatch.setattr(search_service, "genre_names", no_genres)

    filters = SearchFilters(q="busy", by=SearchBy.PERSON, page=3)
    result = asyncio.run(search_service.search(filters, TODAY))
    assert (result.total_pages, result.total_results, result.total_is_estimate) == (3, 130, False)
    assert [m.title for m in result.results] == [f"Film {i}" for i in range(120, 130)]


def test_keywords_combine_with_both_forms_of_each_word(monkeypatch):
    keywords = {
        "alien": [{"id": 1, "name": "alien"}, {"id": 2, "name": "aliens"}, {"id": 3, "name": "alien attack"}],
        "aliens": [{"id": 1, "name": "alien"}, {"id": 2, "name": "aliens"}],
        "small town": [{"id": 9, "name": "small town"}, {"id": 8, "name": "small town girl"}],
    }
    sent = {}

    async def search_keywords(query):
        return keywords[query]

    async def discover_movies(first_page, page_count, **params):
        sent.update(params)
        return {"results": [], "total_pages": 0, "total_results": 0}

    monkeypatch.setattr(tmdb, "search_keywords", search_keywords)
    monkeypatch.setattr(tmdb, "discover_movies", discover_movies)
    monkeypatch.setattr(search_service, "genre_names", no_genres)

    # "All" can't mix "|" into "," on TMDB, so each term uses its best keyword.
    result = asyncio.run(search_service.search(SearchFilters(q="aliens + small town", by=SearchBy.KEYWORD), TODAY))
    assert sent["with_keywords"] == "2,9"
    assert result.matched == "Keywords: aliens + small town"

    any_match = SearchFilters(q="alien, small town", by=SearchBy.KEYWORD, match="any")
    result = asyncio.run(search_service.search(any_match, TODAY))
    assert sent["with_keywords"] == "1|2|9"
    assert result.matched == "Keywords: alien / aliens or small town"


def test_genre_words_in_keyword_search_filter_by_genre(monkeypatch):
    sent = {}

    async def search_keywords(query):
        assert query == "heist", "genre words should not be looked up as keywords"
        return [{"id": 10051, "name": "heist"}]

    async def discover_movies(first_page, page_count, **params):
        sent.clear()
        sent.update(params)
        return {"results": [], "total_pages": 0, "total_results": 0}

    async def genre_names():
        return {35: "Comedy", 80: "Crime"}

    monkeypatch.setattr(tmdb, "search_keywords", search_keywords)
    monkeypatch.setattr(tmdb, "discover_movies", discover_movies)
    monkeypatch.setattr(search_service, "genre_names", genre_names)

    filters = SearchFilters(q="heist + comedy", by=SearchBy.KEYWORD, genre=80)
    result = asyncio.run(search_service.search(filters, TODAY))
    assert (sent["with_keywords"], sent["with_genres"]) == ("10051", "35,80")
    assert result.matched == "Keyword: heist + Comedy (genre)"

    only_genre = SearchFilters(q="comedy", by=SearchBy.KEYWORD)
    assert asyncio.run(search_service.search(only_genre, TODAY)).matched == "Genre: Comedy"
    assert "with_keywords" not in sent


def test_keywords_and_genres_can_be_excluded(monkeypatch):
    sent = {}

    async def search_keywords(query):
        return {
            "alien": [{"id": 1, "name": "alien"}],
            "small town": [{"id": 9, "name": "small town"}],
            "monster": [{"id": 5, "name": "monster"}, {"id": 6, "name": "monsters"}],
        }[query]

    async def discover_movies(first_page, page_count, **params):
        sent.clear()
        sent.update(params)
        return {"results": [], "total_pages": 0, "total_results": 0}

    async def genre_names():
        return {27: "Horror"}

    monkeypatch.setattr(tmdb, "search_keywords", search_keywords)
    monkeypatch.setattr(tmdb, "discover_movies", discover_movies)
    monkeypatch.setattr(search_service, "genre_names", genre_names)

    filters = SearchFilters(q="alien + small town -horror -monster", by=SearchBy.KEYWORD)
    result = asyncio.run(search_service.search(filters, TODAY))
    assert result.matched == "Keywords: alien + small town · without monster / monsters, Horror (genre)"
    assert sent == {
        **{key: sent[key] for key in ("sort_by", "primary_release_date.lte", "vote_count.gte")},
        "with_keywords": "1,9",
        "without_keywords": "5|6",
        "without_genres": "27",
    }

    only_avoiding = SearchFilters(q="-horror", by=SearchBy.KEYWORD)
    assert asyncio.run(search_service.search(only_avoiding, TODAY)).matched == "All movies · without Horror (genre)"


def test_person_search_uses_known_for_role(monkeypatch):
    async def search_people(query):
        return [{"id": 525, "name": "Christopher Nolan", "known_for_department": "Directing"}]

    async def person_movie_credits(person_id):
        return {
            "cast": [movie(10, title="Cameo", character="Himself")],
            "crew": [
                movie(1, title="Inception", job="Director", popularity=50),
                movie(1, title="Inception", job="Writer", popularity=50),
                movie(2, title="Produced Thing", job="Producer"),
            ],
        }

    async def genre_names():
        return {18: "Drama"}

    monkeypatch.setattr(tmdb, "search_people", search_people)
    monkeypatch.setattr(tmdb, "person_movie_credits", person_movie_credits)
    monkeypatch.setattr(search_service, "genre_names", genre_names)

    result = asyncio.run(search_service.search(SearchFilters(q="nolan", by=SearchBy.PERSON), TODAY))
    assert result.matched == "Christopher Nolan · directing"
    assert [(m.title, m.credit, m.genres) for m in result.results] == [("Inception", "Director", ["Drama"])]

    acting = SearchFilters(q="nolan", by=SearchBy.PERSON, role="acting")
    assert asyncio.run(search_service.search(acting, TODAY)).results == []  # "Himself" is not a role
    acting.include_obscure = True
    assert [m.title for m in asyncio.run(search_service.search(acting, TODAY)).results] == ["Cameo"]
