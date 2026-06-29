from sleeper_mcp_server.models import League


def _base(**over):
    d = {
        "league_id": "L", "name": "Test", "season": "2026", "status": "pre_draft",
        "settings": {"num_teams": 12, "playoff_teams": 6}, "roster_positions": ["RB", "WR"],
        "total_rosters": 12,
    }
    d.update(over)
    return d


def test_previous_league_id_parsed_when_present():
    lg = League.model_validate(_base(previous_league_id="PREV123"))
    assert lg.previous_league_id == "PREV123"


def test_previous_league_id_defaults_none():
    lg = League.model_validate(_base())
    assert lg.previous_league_id is None
