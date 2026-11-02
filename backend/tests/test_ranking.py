from app.services.ranking import START_RATING, elo_ratings


def test_winner_rises_and_loser_falls():
    ratings = elo_ratings([(1, 2)])
    assert ratings[1] > START_RATING > ratings[2]


def test_consistent_winner_ranks_first():
    ratings = elo_ratings([(1, 2), (1, 3), (2, 3)])
    assert sorted(ratings, key=ratings.get, reverse=True) == [1, 2, 3]
