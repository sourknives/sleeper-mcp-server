from sleeper_mcp_server import cache as cache_module
from sleeper_mcp_server.cache import CacheManager


class FakeClock:
    """Stands in for the `time` module inside cache.py so TTLs are deterministic."""

    def __init__(self, now: float = 1_000_000.0):
        self._now = now

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_set_then_get_returns_the_value():
    c = CacheManager()
    c.set("league_info:123", {"name": "BDNB"}, 900)
    assert c.get("league_info:123") == {"name": "BDNB"}


def test_get_returns_none_for_an_absent_key():
    assert CacheManager().get("never_written") is None


def test_get_returns_none_once_the_ttl_has_elapsed(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cache_module, "time", clock)

    c = CacheManager()
    c.set("rosters:123", ["a", "b"], 900)

    clock.advance(899)
    assert c.get("rosters:123") == ["a", "b"]

    clock.advance(2)
    assert c.get("rosters:123") is None


def test_set_overwrites_an_existing_key():
    c = CacheManager()
    c.set("matchups:123:4", {"points": 100.0}, 300)
    c.set("matchups:123:4", {"points": 120.5}, 300)
    assert c.get("matchups:123:4") == {"points": 120.5}
