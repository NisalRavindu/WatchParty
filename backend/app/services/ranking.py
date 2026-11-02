START_RATING = 1000.0
K_FACTOR = 32.0


def elo_ratings(comparisons: list[tuple[int, int]]) -> dict[int, float]:
    """Turn (winner_id, loser_id) results, oldest first, into Elo ratings."""
    ratings: dict[int, float] = {}
    for winner, loser in comparisons:
        winner_rating = ratings.get(winner, START_RATING)
        loser_rating = ratings.get(loser, START_RATING)
        expected_win = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
        change = K_FACTOR * (1 - expected_win)
        ratings[winner] = winner_rating + change
        ratings[loser] = loser_rating - change
    return ratings
