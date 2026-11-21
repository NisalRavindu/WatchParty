import math
from itertools import combinations
from typing import NamedTuple

import numpy as np

START_RATING = 1000.0
K_FACTOR = 32.0

# Bradley-Terry prior: strengths start at 0 with this spread (log-odds). It keeps a movie that has
# only ever won from running off to infinity, and is what "not sure yet" means before any games.
PRIOR_SD = 1.0


def elo_ratings(comparisons: list[tuple[int, int]]) -> dict[int, float]:
    """Turn (winner_id, loser_id) results, oldest first, into Elo ratings. Kept as the simple baseline."""
    ratings: dict[int, float] = {}
    for winner, loser in comparisons:
        winner_rating = ratings.get(winner, START_RATING)
        loser_rating = ratings.get(loser, START_RATING)
        expected_win = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
        change = K_FACTOR * (1 - expected_win)
        ratings[winner] = winner_rating + change
        ratings[loser] = loser_rating - change
    return ratings


class Strength(NamedTuple):
    mean: float  # log-odds: A beats B with probability sigmoid(A.mean - B.mean)
    sd: float  # uncertainty of the mean; PRIOR_SD for a movie with no games yet
    games: int


def win_probability(a: float, b: float) -> float:
    return 1 / (1 + math.exp(b - a))


def bradley_terry(comparisons: list[tuple[int, int]], iterations: int = 50) -> dict[int, Strength]:
    """Fit Bradley-Terry strengths to (winner_id, loser_id) results.

    Order doesn't matter, unlike Elo. It's the maximum a posteriori fit under a N(0, PRIOR_SD^2)
    prior, found with Newton's method; the uncertainty comes from the curvature at that point
    (a Laplace approximation).
    """
    ids = sorted({movie for pair in comparisons for movie in pair})
    if not ids:
        return {}
    index = {movie: i for i, movie in enumerate(ids)}
    winners = np.array([index[w] for w, _ in comparisons])
    losers = np.array([index[loser] for _, loser in comparisons])
    n = len(ids)
    prior_precision = np.eye(n) / PRIOR_SD**2

    theta = np.zeros(n)
    for _ in range(iterations):
        p_win = 1 / (1 + np.exp(theta[losers] - theta[winners]))  # chance the actual winner wins
        gradient = -prior_precision @ theta
        np.add.at(gradient, winners, 1 - p_win)
        np.subtract.at(gradient, losers, 1 - p_win)
        information = _information(n, winners, losers, p_win) + prior_precision
        step = np.linalg.solve(information, gradient)
        theta += step
        if np.abs(step).max() < 1e-9:
            break

    p_win = 1 / (1 + np.exp(theta[losers] - theta[winners]))
    covariance = np.linalg.inv(_information(n, winners, losers, p_win) + prior_precision)
    games = np.bincount(np.concatenate([winners, losers]), minlength=n)
    return {
        movie: Strength(float(theta[i]), float(math.sqrt(covariance[i, i])), int(games[i]))
        for movie, i in index.items()
    }


def _information(n: int, winners: np.ndarray, losers: np.ndarray, p_win: np.ndarray) -> np.ndarray:
    """Fisher information of the comparisons: each game ties its two movies' strengths together."""
    weight = p_win * (1 - p_win)
    information = np.zeros((n, n))
    np.add.at(information, (winners, winners), weight)
    np.add.at(information, (losers, losers), weight)
    np.subtract.at(information, (winners, losers), weight)
    np.subtract.at(information, (losers, winners), weight)
    return information


def unrated() -> Strength:
    return Strength(0.0, PRIOR_SD, 0)


def pair_information(a: Strength, b: Strength) -> float:
    """How much a game between a and b is expected to teach: close matchups between uncertain movies."""
    p = win_probability(a.mean, b.mean)
    return p * (1 - p) * (a.sd**2 + b.sd**2)


def most_informative_pairs(strengths: dict[int, Strength]) -> list[tuple[int, int]]:
    """Pair up the movies (an even number) greedily, most informative matchup first."""
    left = set(strengths)
    scored = sorted(
        combinations(sorted(strengths), 2),
        key=lambda pair: pair_information(strengths[pair[0]], strengths[pair[1]]),
        reverse=True,
    )
    pairs = []
    for a, b in scored:
        if a in left and b in left:
            pairs.append((a, b))
            left -= {a, b}
    return pairs
