"""El limitador de tasa mantiene sus límites y su ventana, y no crece sin límite en memoria."""

from conftest import FakeClock
from copiloto.ratelimit import SlidingWindowLimiter


def test_limiter_blocks_within_the_window():
    clock = FakeClock(1000.0)
    limiter = SlidingWindowLimiter(2, window_s=60, clock=clock)
    assert limiter.check("a") is None
    assert limiter.check("a") is None
    wait = limiter.check("a")
    assert wait is not None and 0 < wait <= 60


def test_a_key_starts_fresh_once_its_window_passed():
    clock = FakeClock(1000.0)
    limiter = SlidingWindowLimiter(2, window_s=60, clock=clock)
    limiter.check("a")
    limiter.check("a")
    clock.advance(61)
    assert limiter.check("a") is None


def test_pruning_keeps_keys_that_are_still_inside_their_window():
    clock = FakeClock(1000.0)
    limiter = SlidingWindowLimiter(2, window_s=60, clock=clock)
    for index in range(10_005):  # claves que quedarán vencidas
        limiter.check(f"stale-{index}")
    clock.advance(30)
    limiter.check("a")
    limiter.check("a")  # clave activa dentro de la ventana
    clock.advance(31)  # las viejas vencen (61 s); «a» sigue viva (31 s)
    assert limiter.check("stale-x") is None  # inserta una clave y dispara la poda
    assert limiter.check("a") is not None, "los cupos del huésped activo sobreviven a la poda"


def test_old_keys_are_pruned_so_memory_stays_bounded():
    clock = FakeClock(1000.0)
    limiter = SlidingWindowLimiter(2, window_s=60, clock=clock)
    for index in range(10_005):
        limiter.check(f"key-{index}")
    clock.advance(61)
    limiter.check("fresh")
    assert len(limiter._hits) <= 2, "las claves vencidas no deben acumularse para siempre"
