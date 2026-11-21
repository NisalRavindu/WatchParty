import random

from app.services.brackets import seed
from app.services.ranking import (
    PRIOR_SD,
    START_RATING,
    Strength,
    bradley_terry,
    elo_ratings,
    most_informative_pairs,
    pair_information,
    unrated,
    win_probability,
)


def test_winner_rises_and_loser_falls():
    ratings = elo_ratings([(1, 2)])
    assert ratings[1] > START_RATING > ratings[2]


def test_consistent_winner_ranks_first():
    ratings = elo_ratings([(1, 2), (1, 3), (2, 3)])
    assert sorted(ratings, key=ratings.get, reverse=True) == [1, 2, 3]


def test_bradley_terry_orders_and_ignores_game_order():
    games = [(1, 2), (1, 3), (2, 3), (1, 2)]
    strengths = bradley_terry(games)
    assert sorted(strengths, key=lambda m: strengths[m].mean, reverse=True) == [1, 2, 3]
    assert bradley_terry(list(reversed(games))) == strengths  # unlike Elo, order doesn't matter
    assert [strengths[m].games for m in (1, 2, 3)] == [3, 3, 2]


def test_an_unbeaten_movie_stays_finite_and_uncertain():
    strengths = bradley_terry([(1, 2)])
    assert 0 < strengths[1].mean < 1 and strengths[2].mean == -strengths[1].mean
    assert strengths[1].sd < PRIOR_SD  # one game teaches a little


def test_more_games_mean_less_uncertainty():
    few = bradley_terry([(1, 2), (2, 1)])
    many = bradley_terry([(1, 2), (2, 1)] * 10)
    assert many[1].sd < few[1].sd
    assert abs(many[1].mean) < 1e-9  # an even record is an even match


def test_win_probability_matches_the_fitted_record():
    strengths = bradley_terry([(1, 2)] * 30 + [(2, 1)] * 10)
    p = win_probability(strengths[1].mean, strengths[2].mean)
    assert 0.65 < p < 0.75  # 30 of 40, pulled slightly towards 50/50 by the prior


def test_close_uncertain_matchups_are_most_informative():
    settled_gap = pair_information(Strength(2, 0.2, 40), Strength(-2, 0.2, 40))
    assert pair_information(unrated(), unrated()) > settled_gap
    strengths = {1: Strength(2, 0.3, 9), 2: Strength(1.9, 0.3, 9), 3: Strength(-2, 0.3, 9), 4: Strength(-1.9, 0.3, 9)}
    assert sorted(map(sorted, most_informative_pairs(strengths))) == [[1, 2], [3, 4]]


def test_seeding_mixes_seen_and_well_known_movies():
    rng = random.Random(0)
    seen = [1, 2, 3, 4, 5, 6]
    strengths = {1: Strength(0, 0.2, 30), 2: Strength(0, 0.9, 1)}  # 1 is settled; 3-6 never played
    pairs, reserves = seed(seen, [1, 10, 11, 12, 13, 14, 15], strengths, 8, rng)
    played = {movie for pair in pairs for movie in pair}
    assert len(pairs) == 4 and len(played) == 8
    assert len(played & set(seen)) == 4 and 1 not in played  # the least settled seen movies play
    assert set(reserves) == {10, 11, 12, 13, 14, 15} - played

    # Too few well-known movies: more seen ones fill in. Too few movies overall: a smaller field.
    assert len(seed(seen, [], {}, 8, rng).pairs) == 3
