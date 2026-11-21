def library(client):
    return [(item["movie"]["id"], item["seen"], item["intent"]) for item in client.get("/api/library").json()]


def test_library_entry_lifecycle(client):
    response = client.patch("/api/library/10", json={"intent": "curious"})
    assert response.status_code == 200
    assert response.json()["movie"]["title"] == "Movie 10"

    # Promoting Curious to Want changes the intent; it is still one entry.
    client.patch("/api/library/10", json={"intent": "want"})
    assert library(client) == [(10, False, "want")]

    # Watching it fulfils the Want.
    client.patch("/api/library/10", json={"seen": True})
    assert library(client) == [(10, True, None)]

    # Wanting a seen movie again is a rewatch: seen and want at once.
    client.patch("/api/library/10", json={"intent": "want"})
    assert library(client) == [(10, True, "want")]

    assert client.patch("/api/library/10", json={"intent": "curious"}).status_code == 422
    assert client.patch("/api/library/10", json={"intent": "bucket"}).status_code == 422

    assert client.delete("/api/library/10").status_code == 204
    assert library(client) == []
    assert client.delete("/api/library/10").status_code == 404


def test_unsetting_everything_removes_the_entry(client):
    client.patch("/api/library/3", json={"seen": True})
    client.patch("/api/library/3", json={"seen": False})
    assert library(client) == []


def test_library_changes_are_logged_as_signals(client):
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Signal

    client.patch("/api/library/7", json={"intent": "curious"})
    client.patch("/api/library/7", json={"seen": True})
    client.patch("/api/library/7", json={"seen": True})  # no change, no signal
    client.delete("/api/library/7")

    with Session(engine) as session:
        signals = session.exec(select(Signal).order_by(Signal.id)).all()
    assert [(s.kind, s.context) for s in signals] == [
        ("status_set", {"seen": False, "intent": "curious", "previous": {"seen": False, "intent": None}}),
        ("status_set", {"seen": True, "intent": None, "previous": {"seen": False, "intent": "curious"}}),
        ("status_cleared", {"previous": {"seen": True, "intent": None}}),
    ]


def test_bracket_results_become_rankings(client):
    for winner, loser in [(1, 2), (1, 3), (2, 3)]:
        response = client.post("/api/games/comparisons", json={"winner_id": winner, "loser_id": loser})
        assert response.status_code == 201

    ranked = client.get("/api/games/rankings").json()
    assert [entry["movie"]["id"] for entry in ranked] == [1, 2, 3]
    assert [entry["games"] for entry in ranked] == [2, 2, 2]
    assert all(0 < entry["sd"] < 1 for entry in ranked)


def test_playing_a_matchup_means_both_were_seen(client):
    client.patch("/api/library/2", json={"intent": "want"})
    client.post("/api/games/comparisons", json={"winner_id": 1, "loser_id": 2, "topic": "Better ending"})
    assert sorted(library(client)) == [(1, True, None), (2, True, None)]  # watching fulfilled the Want
    assert client.get("/api/games/rankings?topic=Other").json() == []


def test_bracket_skips_movies_they_have_not_seen(client, monkeypatch):
    from app.models import Movie
    from app.services import brackets

    async def well_known_movies(rng):
        return [Movie(id=i, title=f"Famous {i}") for i in range(100, 112)]

    monkeypatch.setattr(brackets, "well_known_movies", well_known_movies)
    client.patch("/api/library/1", json={"seen": True})
    client.patch("/api/library/100", json={"intent": "want"})  # on their list, so not seen
    client.post("/api/games/not-seen", json={"movie_id": 101, "topic": "Better ending"})

    bracket = client.post("/api/games/brackets", json={"topic": "Better ending"}).json()
    played = [movie["id"] for pair in bracket["pairs"] for movie in pair]
    assert len(played) == len(set(played)) == 8
    assert 1 in played and not {100, 101} & set(played + [m["id"] for m in bracket["reserves"]])
    assert client.post("/api/games/brackets", json={"size": 7}).status_code == 422


def test_session_keeps_context_and_pick_together(client):
    session_id = client.post("/api/sessions").json()["id"]

    response = client.post(
        "/api/games/name-three",
        json={"prompt": "feels like tonight", "movie_ids": [1, 2, 3], "session_id": session_id},
    )
    assert response.status_code == 201
    assert client.post(f"/api/sessions/{session_id}/pick", json={"movie_id": 4}).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/pick", json={"movie_id": 5}).status_code == 409

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["session"]["picked_movie_id"] == 4
    assert [signal["kind"] for signal in detail["signals"]] == ["named"] * 3 + ["picked"]


def test_shortlist_then_pick(client):
    session_id = client.post("/api/sessions").json()["id"]
    for movie_id in (1, 2, 3):
        response = client.post(f"/api/sessions/{session_id}/candidates", json={"movie_id": movie_id})
        assert response.status_code == 201
        assert response.json()["title"] == f"Movie {movie_id}"
    assert client.delete(f"/api/sessions/{session_id}/candidates/3").status_code == 204
    assert client.post(f"/api/sessions/{session_id}/pick", json={"movie_id": 2}).status_code == 200

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert [movie["id"] for movie in detail["candidates"]] == [1, 2]
    assert [signal["kind"] for signal in detail["signals"]] == ["shortlisted"] * 3 + ["unshortlisted", "picked"]

    # A decided session is closed for edits.
    assert client.post(f"/api/sessions/{session_id}/candidates", json={"movie_id": 5}).status_code == 409
    assert client.get("/api/sessions").json()[0]["id"] == session_id


def test_examples_say_what_tonight_is_and_is_not(client):
    session_id = client.post("/api/sessions").json()["id"]
    examples = f"/api/sessions/{session_id}/examples"
    assert client.put(examples, json={"movie_id": 1, "positive": True}).status_code == 200
    client.put(examples, json={"movie_id": 2, "positive": True})
    client.put(examples, json={"movie_id": 2, "positive": True})  # no change, no signal
    client.put(examples, json={"movie_id": 2, "positive": False})  # changed my mind
    client.put(examples, json={"movie_id": 3, "positive": False})
    assert client.delete(f"{examples}/3").status_code == 204
    assert client.delete(f"{examples}/3").status_code == 404

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert [(e["movie"]["id"], e["positive"]) for e in detail["examples"]] == [(1, True), (2, False)]
    assert detail["candidates"] == []  # examples are context, not candidates
    assert [(s["kind"], s["movie_id"], s["value"]) for s in detail["signals"]] == [
        ("example_set", 1, 1.0),
        ("example_set", 2, 1.0),
        ("example_set", 2, -1.0),
        ("example_set", 3, -1.0),
        ("example_removed", 3, 1.0),
    ]

    client.post(f"/api/sessions/{session_id}/pick", json={"movie_id": 4})
    assert client.put(examples, json={"movie_id": 5, "positive": True}).status_code == 409


def test_dashboard_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "WatchParty" in response.text
