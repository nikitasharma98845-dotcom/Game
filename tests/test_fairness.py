from __future__ import annotations

import hashlib
import hmac

from bot.core.fairness import FairRNG, hash_server_seed, new_server_seed


def test_same_seed_and_nonce_reproduce_identical_stream():
    seed = new_server_seed()
    a = FairRNG(seed, "client-seed", 7)
    b = FairRNG(seed, "client-seed", 7)
    assert a.floats(200) == b.floats(200)
    assert a.proof == b.proof


def test_hmac_scheme_matches_spec():
    seed = "00" * 32
    rng = FairRNG(seed, "abc", 3)
    for cursor in range(5):
        expected = hmac.new(
            bytes.fromhex(seed), f"abc:3:{cursor}".encode(), hashlib.sha256
        ).digest()[:4]
        value = rng.next()
        assert value == int.from_bytes(expected, "big") / 4294967296.0
        assert rng.proof[cursor] == expected.hex()


def test_different_nonce_changes_outcome():
    seed = new_server_seed()
    a = FairRNG(seed, "abc", 1).floats(10)
    b = FairRNG(seed, "abc", 2).floats(10)
    assert a != b


def test_ints_are_in_range():
    rng = FairRNG(new_server_seed(), "abc", 0)
    values = [rng.int(6) for _ in range(5_000)]
    assert set(values) <= {0, 1, 2, 3, 4, 5}
    assert {0, 1, 2, 3, 4, 5} <= set(values)


def test_shuffle_is_deterministic_and_a_permutation():
    seed = new_server_seed()
    a = FairRNG(seed, "abc", 0).shuffle(list(range(30)))
    b = FairRNG(seed, "abc", 0).shuffle(list(range(30)))
    assert a == b
    assert sorted(a) == list(range(30))


def test_hash_is_sha256_of_raw_seed():
    seed = new_server_seed()
    assert hash_server_seed(seed) == hashlib.sha256(bytes.fromhex(seed)).hexdigest()


def test_floats_are_unit_interval():
    rng = FairRNG(new_server_seed(), "abc", 0)
    values = rng.floats(10_000)
    assert all(0.0 <= v < 1.0 for v in values)
    mean = sum(values) / len(values)
    assert abs(mean - 0.5) < 0.02
