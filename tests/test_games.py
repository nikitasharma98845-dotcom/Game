from __future__ import annotations

import pytest

from bot.core.errors import GameError
from bot.games import all_games, get_game
from bot.games.blackjack import card_value, hand_value
from bot.games.roulette import bet_wins
from bot.games.tables import comb, hypergeom, scale_to_rtp, table_rtp, weighted_table
from bot.games.video_poker import evaluate
from tests.sim import FastRNG


def test_every_game_starts_and_renders():
    rng = FastRNG(11)
    for game in all_games():
        if game.key == "duel":
            with pytest.raises(GameError):
                game.start(rng, {}, 100)
            continue
        if game.key == "roulette":
            # Roulette is started from the bet-slip flow, not a preset.
            assert game.quick_starts()
            continue
        starters = game.quick_starts()
        assert starters, game.key
        starter = starters[0]
        params = game.validate(dict(starter.params))
        rnd = game.start(rng, params, 100)
        assert rnd.text, game.key
        assert rnd.multiplier >= 0, game.key
        if not game.multi_step:
            assert rnd.finished, game.key


def test_dice_multiplier_and_chance():
    game = get_game("dice")
    params = game.validate({"direction": "under", "target": "50"})
    rnd = game.start(FastRNG(1), params, 100)
    assert rnd.multiplier in (0.0, pytest.approx(1.98, abs=0.001))
    with pytest.raises(GameError):
        game.validate({"direction": "sideways", "target": "50"})
    with pytest.raises(GameError):
        game.validate({"direction": "under", "target": "1"})


def test_limbo_target_payout():
    game = get_game("limbo")
    params = game.validate({"target": "2"})
    for _ in range(50):
        rnd = game.start(FastRNG(3), params, 100)
        assert rnd.multiplier in (0.0, 2.0)


def test_mines_multiplier_matches_probability():
    from bot.games.mines import mines_multiplier

    for mines in (1, 3, 10):
        for revealed in range(1, 25 - mines):
            probability = comb(25 - mines, revealed) / comb(25, revealed)
            expected = (0.99 / probability) if probability > 0 else 1.0
            assert mines_multiplier(mines, revealed) == pytest.approx(expected, rel=0.002)


def test_plinko_board_structure():
    game = get_game("plinko")
    rnd = game.start(FastRNG(4), game.validate({"rows": "12", "risk": "medium"}), 100)
    assert len(rnd.detail["path"]) == 12
    assert rnd.detail["slot"] == rnd.detail["path"].count("R")
    assert len(rnd.detail["table"]) == 13


def test_wheel_segments_and_rtp():
    from bot.games.wheel import wheel_values

    values = wheel_values(20, "medium")
    assert len(values) == 20
    assert sum(values) / len(values) == pytest.approx(0.99, abs=0.005)


def test_roulette_wins_and_pays():
    assert bet_wins("color", "red", 1)
    assert not bet_wins("color", "red", 2)
    assert not bet_wins("color", "red", 0)
    assert bet_wins("straight", [17], 17)
    assert bet_wins("split", [1, 2], 2)
    assert bet_wins("street", [1, 2, 3], 3)
    assert bet_wins("corner", [1, 2, 4, 5], 5)
    assert bet_wins("line", [1, 2, 3, 4, 5, 6], 6)
    assert bet_wins("dozen", "2", 13)
    assert bet_wins("column", "3", 3)
    assert bet_wins("parity", "odd", 7)
    assert bet_wins("half", "high", 30)


def test_roulette_slip_total_must_match_stake():
    game = get_game("roulette")
    params = game.validate({"bets": [{"type": "color", "sel": "red", "amount": 100}]})
    with pytest.raises(GameError):
        game.start(FastRNG(1), params, 200)
    rnd = game.start(FastRNG(1), params, 100)
    assert rnd.multiplier in (0.0, 2.0)


def test_blackjack_values_and_soft_aces():
    assert hand_value([["A", "♠"], ["K", "♥"]])[0] == 21
    assert hand_value([["A", "♠"], ["A", "♥"], ["9", "♦"]])[0] == 21
    assert hand_value([["A", "♠"], ["A", "♥"], ["9", "♦"]])[1] is True
    assert hand_value([["10", "♠"], ["J", "♥"], ["Q", "♦"]])[0] == 30
    assert card_value("A") == 11


def test_blackjack_round_completes():
    from tests.sim import blackjack_action

    game = get_game("blackjack")
    for seed in range(20):
        rng = FastRNG(seed)
        rnd = game.start(rng, {}, 100)
        steps = 0
        while not rnd.finished and steps < 40:
            action, arg = blackjack_action(game, rnd.state)
            rnd = game.step(rnd.state, action, arg, rng)
            steps += 1
        assert rnd.finished
        assert 0 <= rnd.multiplier <= 3
        assert rnd.text


def test_video_poker_categories():
    def cards(spec):
        return [[r, s] for r, s in spec]

    assert evaluate(cards([("10", "♠"), ("J", "♠"), ("Q", "♠"), ("K", "♠"), ("A", "♠")])) == "royal_flush"
    assert evaluate(cards([("9", "♠"), ("10", "♠"), ("J", "♠"), ("Q", "♠"), ("K", "♠")])) == "straight_flush"
    assert evaluate(cards([("7", "♠"), ("7", "♥"), ("7", "♦"), ("7", "♣"), ("K", "♠")])) == "four"
    assert evaluate(cards([("7", "♠"), ("7", "♥"), ("7", "♦"), ("K", "♣"), ("K", "♠")])) == "full_house"
    assert evaluate(cards([("2", "♠"), ("5", "♠"), ("9", "♠"), ("J", "♠"), ("K", "♠")])) == "flush"
    assert evaluate(cards([("5", "♠"), ("6", "♥"), ("7", "♦"), ("8", "♣"), ("9", "♠")])) == "straight"
    assert evaluate(cards([("Q", "♠"), ("Q", "♥"), ("Q", "♦"), ("3", "♣"), ("9", "♠")])) == "three"
    assert evaluate(cards([("J", "♠"), ("J", "♥"), ("4", "♦"), ("4", "♣"), ("9", "♠")])) == "two_pair"
    assert evaluate(cards([("J", "♠"), ("J", "♥"), ("4", "♦"), ("7", "♣"), ("9", "♠")])) == "jacks"
    assert evaluate(cards([("10", "♠"), ("10", "♥"), ("4", "♦"), ("7", "♣"), ("9", "♠")])) == "none"


def test_keno_table_rtp_and_probabilities():
    from bot.games.keno import keno_paid_hits, keno_table

    for picks in (1, 5, 10):
        rtp = sum(hypergeom(40, 10, picks, h) * m for h, m in keno_table(picks, "classic"))
        assert rtp == pytest.approx(0.99, abs=0.01)
    assert keno_paid_hits(5, "classic")


def test_keno_draw_is_ten_unique_numbers():
    game = get_game("keno")
    rnd = game.start(FastRNG(5), game.validate({"picks": "5", "risk": "classic"}), 100)
    assert len(set(rnd.detail["drawn"])) == 10
    assert len(set(rnd.detail["chosen"])) == 5


def test_diamond_pattern_odds_sum_to_one():
    from bot.games.diamonds import diamond_odds, diamond_table

    odds = diamond_odds()
    assert sum(odds.values()) == pytest.approx(1.0)
    assert sum(odds[p] * m for p, m in diamond_table().items()) == pytest.approx(0.99, abs=0.01)


def test_tarot_combined_multiplier_matches_cards():
    game = get_game("tarot")
    rnd = game.start(FastRNG(6), {}, 100)
    expected = 1.0
    for value in rnd.detail["values"]:
        expected *= value
    assert rnd.multiplier == pytest.approx(expected, abs=0.02)


def test_sicbo_payout_table():
    game = get_game("sicbo")
    assert game._payout("triple:6", [6, 6, 6]) == 181
    assert game._payout("any_triple", [6, 6, 6]) == 31
    assert game._payout("small", [6, 6, 6]) == 0
    assert game._payout("big", [4, 5, 6]) == 2
    assert game._payout("combo:2-5", [2, 5, 1]) == 6
    assert game._payout("double:5", [5, 5, 1]) == 11


def test_slots_grid_and_rtp():
    from bot.games.slots import theme_tables

    for key in ("pharaoh", "ronin", "spellbook"):
        game = get_game(key)
        rnd = game.start(FastRNG(8), {}, 100)
        assert len(rnd.detail["grid"]) == 5
        assert all(len(column) == 3 for column in rnd.detail["grid"])
        pays, trigger, rtp = theme_tables(game.theme_key)
        assert 0.97 <= rtp <= 1.01
        assert 0 < trigger < 0.1
        assert pays


def test_crash_point_is_at_least_one():
    from bot.games.crash import crash_point

    for seed in range(100):
        assert crash_point(FastRNG(seed)) >= 1.0


def test_tables_helpers():
    values = scale_to_rtp([1.0, 0.5, 2.0], edge=0.01)
    assert sum(values) / len(values) == pytest.approx(0.99, abs=0.01)
    table = weighted_table([2.0, 5.0], [0.7, 0.3], zero_prob=0.5)
    assert sum(p for _, p in table) == pytest.approx(1.0)
    assert table_rtp(table) == pytest.approx(0.99, abs=0.01)


def test_multi_step_games_auto_settle():
    for key in ("mines", "hilo", "dragontower", "pump", "chicken", "moles", "snakes", "coinflip"):
        game = get_game(key)
        starter = game.quick_starts()[0]
        rnd = game.start(FastRNG(9), game.validate(dict(starter.params)), 100)
        assert not rnd.finished
        assert rnd.buttons
        settled = game.auto_settle(rnd.state)
        assert settled.finished
        assert settled.multiplier >= 0
        assert settled.text


def test_invalid_params_raise():
    assert get_game("dice").validate({"direction": "under", "target": "50"})
    for key, params in [
        ("mines", {"mines": "25"}),
        ("limbo", {"target": "0.5"}),
        ("plinko", {"rows": "30", "risk": "low"}),
        ("wheel", {"segments": "99", "risk": "low"}),
        ("keno", {"picks": "11", "risk": "low"}),
        ("baccarat", {"bet": "draw"}),
        ("sicbo", {"bet": "nope"}),
        ("bars", {"bar": "4", "risk": "low"}),
        ("cases", {"case": "nope"}),
        ("roulette", {"bets": []}),
    ]:
        with pytest.raises(GameError):
            get_game(key).validate(params)
