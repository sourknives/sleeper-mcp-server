from sleeper_mcp_server.models import Matchup, PlayerStats, Roster


def test_matchup_does_not_raise_when_starter_not_in_players():
    # Real data: a mid-week-dropped starter may not be in players.
    m = Matchup.model_validate({
        "matchup_id": 1, "roster_id": 1, "points": 100.0,
        "players": ["A", "B"], "starters": ["A", "C"],
    })
    assert m.roster_id == 1
    assert "C" in m.starters


def test_player_stats_allows_empty_stats():
    ps = PlayerStats(player_id="4046", season="2025", stats={})
    assert ps.stats == {}


def test_roster_captures_keepers_and_player_map():
    r = Roster.model_validate({
        "roster_id": 1, "owner_id": "u1", "league_id": "l1",
        "players": ["A", "B"], "starters": ["A"],
        "keepers": ["A"], "player_map": {"A": {"number": 17}},
    })
    assert r.keepers == ["A"]
    assert r.player_map == {"A": {"number": 17}}
