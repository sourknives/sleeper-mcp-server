"""Season/week resolution helpers built on /state/nfl."""

from .models import NflState


def resolve_default_season(state: NflState) -> str:
    """Resolve the season tools should default to.

    During the offseason the calendar season often has no leagues yet
    (e.g., in June 2026 a user's 2026 leagues don't exist), so fall back
    to the most recent completed season.
    """
    if state.season_type == "off" and state.previous_season:
        return state.previous_season
    return state.season
