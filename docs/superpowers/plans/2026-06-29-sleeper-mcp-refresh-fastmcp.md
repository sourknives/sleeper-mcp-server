# Sleeper MCP Refresh (FastMCP, Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the Sleeper MCP server so every tool returns correct, current-season data on a modern FastMCP foundation.

**Architecture:** Keep the layered package (`client → cache → models → tools`). Rewrite the server layer from the low-level `mcp.server.Server` API to **FastMCP** with a lifespan-managed `SleeperClient`/`CacheManager`. Fix correctness bugs (broken `get_player_stats`, hardcoded `"2024"` season, over-strict models, redundant ~15 MB catalog fetches), remove the two cosmetic trade tools, and return structured data instead of pre-formatted markdown.

**Tech Stack:** Python ≥3.10, `mcp` (FastMCP) ≥1.28 <2.0, `httpx`, `pydantic` v2, `pytest` + `pytest-asyncio`.

## Global Constraints

- Python: `requires-python = ">=3.10"` (the `mcp` SDK floor). Drop 3.8/3.9 everywhere.
- SDK pin: `mcp>=1.28,<2.0`.
- All tools are **read-only** GETs → every tool annotated `ToolAnnotations(readOnlyHint=True)`.
- **Structured output:** tools return Pydantic models or `dict[str, Any]` (never a bare `dict` — verified against mcp 1.28: a bare `dict` annotation leaves `structuredContent` empty, while `dict[str, Any]` and Pydantic models populate it). Never pre-formatted markdown strings. No `_format_*` methods in the new server.
- Transport: **stdio**, logging to **stderr only** (never stdout — it corrupts the MCP stream).
- Sleeper API: base `https://api.sleeper.app/v1` for everything except player stats/projections, which use host `https://api.sleeper.com` (no `/v1`).
- Season is resolved dynamically; tools still accept an explicit `season` override.
- DRY, YAGNI, TDD, frequent commits.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `pyproject.toml` | Packaging, deps, tool config | Modify |
| `sleeper_mcp_server/models.py` | Pydantic models | Modify (relax validators, add `NflState`, drop unused trade models) |
| `sleeper_mcp_server/sleeper_client.py` | HTTP client | Modify (add `get_nfl_state`, fix stats endpoint, client-level player cache) |
| `sleeper_mcp_server/nfl_state.py` | Season/week resolution | **Create** |
| `sleeper_mcp_server/tools/player_tools.py` | Player tools | Modify (fix `get_player_stats`) |
| `sleeper_mcp_server/tools/trade_tools.py` | Trade tools | **Delete** |
| `sleeper_mcp_server/server.py` | MCP server | **Rewrite** as FastMCP app |
| `sleeper_mcp_server/__main__.py` | Entry point | Modify (run FastMCP) |
| `tests/test_nfl_state.py` | Resolver tests | **Create** |
| `tests/test_models.py` | Model-relaxation tests | **Create** |
| `tests/test_player_tools.py` | Player tool tests | **Create** |
| `tests/test_server_integration.py` | In-memory MCP client tests | **Create** |
| `README.md` | Docs | Modify (tool list, install, config) |

---

## Task 1: Fix packaging and set up the dev environment

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: an installable package on Python ≥3.10 with FastMCP importable.

- [ ] **Step 1: Edit `pyproject.toml`**

Change `requires-python` and the dependency pin, and drop 3.8/3.9. In `[project]`:

```toml
requires-python = ">=3.10"
```

In `classifiers`, remove the `3.8` and `3.9` lines, keeping `3.10`–`3.12` (add `3.13`):

```toml
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
```

In `dependencies`, pin mcp:

```toml
dependencies = [
    "mcp>=1.28,<2.0",
    "httpx>=0.25.0",
    "pydantic>=2.0.0",
    "typing-extensions>=4.0.0",
]
```

In `[tool.black]` set `target-version = ['py310']`; in `[tool.mypy]` set `python_version = "3.10"`.

- [ ] **Step 2: Create the venv and install**

Run:
```bash
python3 --version   # expect 3.10+ (3.13 locally)
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```
Expected: install completes without the "requires-python" conflict.

- [ ] **Step 3: Verify FastMCP imports**

Run:
```bash
. .venv/bin/activate && python -c "from mcp.server.fastmcp import FastMCP, Context; from mcp.types import ToolAnnotations; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: require Python >=3.10, pin mcp>=1.28,<2.0"
```

> Note: `.venv/` is already covered by `.gitignore`. All later `pytest`/`python` commands assume the venv is activated.

---

## Task 2: Add `NflState` model and `SleeperClient.get_nfl_state()`

**Files:**
- Modify: `sleeper_mcp_server/models.py`
- Modify: `sleeper_mcp_server/sleeper_client.py`
- Test: `tests/test_nfl_state.py`

**Interfaces:**
- Produces: `NflState` (pydantic model) with fields `season: str`, `season_type: str`, `week: int`, `display_week: int`, `previous_season: str`; `SleeperClient.get_nfl_state(sport="nfl") -> NflState`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_nfl_state.py`:

```python
import pytest
from unittest.mock import AsyncMock
from sleeper_mcp_server.sleeper_client import SleeperClient
from sleeper_mcp_server.models import NflState


@pytest.mark.asyncio
async def test_get_nfl_state_parses_state_payload():
    client = SleeperClient()
    client._make_request = AsyncMock(return_value={
        "week": 0, "leg": 0, "season": "2026", "season_type": "off",
        "previous_season": "2025", "display_week": 1,
    })
    state = await client.get_nfl_state()
    await client.close()

    assert isinstance(state, NflState)
    assert state.season == "2026"
    assert state.season_type == "off"
    assert state.previous_season == "2025"
    assert state.display_week == 1
    client._make_request.assert_awaited_once_with("GET", "/state/nfl")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nfl_state.py::test_get_nfl_state_parses_state_payload -v`
Expected: FAIL — `ImportError: cannot import name 'NflState'`.

- [ ] **Step 3: Add the `NflState` model**

In `sleeper_mcp_server/models.py`, after the imports, add:

```python
class NflState(BaseModel):
    """Model for the /state/<sport> endpoint."""
    season: str = Field(..., description="Active season year")
    season_type: str = Field(..., description="pre, regular, post, or off")
    week: int = Field(default=0, description="Current week (0 in offseason)")
    display_week: int = Field(default=1, description="Week to display in UI")
    previous_season: Optional[str] = Field(None, description="Prior season year")
    leg: Optional[int] = Field(None, description="Current leg")
```

- [ ] **Step 4: Add the client method**

In `sleeper_mcp_server/sleeper_client.py`, import `NflState` (add to the existing `from .models import (...)` block) and add this method near the other endpoint methods:

```python
    async def get_nfl_state(self, sport: str = "nfl") -> NflState:
        """Get current season/week state for a sport."""
        data = await self._make_request("GET", f"/state/{sport}")
        return NflState.model_validate(data)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_nfl_state.py::test_get_nfl_state_parses_state_payload -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sleeper_mcp_server/models.py sleeper_mcp_server/sleeper_client.py tests/test_nfl_state.py
git commit -m "feat: add NflState model and get_nfl_state client method"
```

---

## Task 3: Season resolver (`nfl_state.py`)

**Files:**
- Create: `sleeper_mcp_server/nfl_state.py`
- Test: `tests/test_nfl_state.py` (append)

**Interfaces:**
- Consumes: `NflState` (Task 2).
- Produces: `resolve_default_season(state: NflState) -> str` — returns `state.previous_season` when `season_type == "off"` (and a previous season exists), else `state.season`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_nfl_state.py`:

```python
from sleeper_mcp_server.nfl_state import resolve_default_season


def _state(**kw):
    base = {"season": "2026", "season_type": "regular", "week": 3,
            "display_week": 3, "previous_season": "2025"}
    base.update(kw)
    return NflState.model_validate(base)


def test_resolver_uses_current_season_in_season():
    assert resolve_default_season(_state(season_type="regular")) == "2026"


def test_resolver_falls_back_to_previous_in_offseason():
    assert resolve_default_season(_state(season_type="off")) == "2025"


def test_resolver_uses_current_when_no_previous():
    assert resolve_default_season(_state(season_type="off", previous_season=None)) == "2026"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_nfl_state.py -k resolver -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sleeper_mcp_server.nfl_state'`.

- [ ] **Step 3: Create the resolver**

Create `sleeper_mcp_server/nfl_state.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_nfl_state.py -k resolver -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add sleeper_mcp_server/nfl_state.py tests/test_nfl_state.py
git commit -m "feat: add season resolver with offseason fallback"
```

---

## Task 4: Relax over-strict models; drop unused trade models

**Files:**
- Modify: `sleeper_mcp_server/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Matchup` that does not raise on `starters ⊄ players`; `PlayerStats` that accepts empty `stats`; `Roster` exposing `keepers` and `player_map`. Removes `TradeProposal`, `TradeAnalysis`, `RosterAnalysis`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `test_matchup...` raises `ValidationError` ("All starters must be in the players list"); `test_player_stats...` raises ("Stats cannot be empty"); `test_roster...` AttributeError on `keepers`.

- [ ] **Step 3: Relax `Matchup`**

In `sleeper_mcp_server/models.py`, replace the `Matchup.validate_starters_in_players` model_validator body so it warns instead of raising:

```python
    @model_validator(mode='after')
    def validate_starters_in_players(self):
        """Warn (do not raise) when starters aren't all in players.

        Real data violates this when a starter is dropped mid-week.
        """
        if self.players and self.starters:
            missing = set(self.starters) - set(self.players)
            if missing:
                import logging
                logging.getLogger(__name__).warning(
                    f"Matchup roster {self.roster_id}: starters not in players: {missing}"
                )
        return self
```

- [ ] **Step 4: Relax `PlayerStats`**

Remove the `validate_stats` validator (it forbade empty stats). Delete this block entirely:

```python
    @field_validator('stats')
    @classmethod
    def validate_stats(cls, v):
        """Validate that stats dictionary is not empty."""
        if not v:
            raise ValueError("Stats cannot be empty")
        return v
```

Also widen the `week` bound to allow playoffs/extended weeks: change `week: Optional[int] = Field(None, ge=1, le=18, ...)` to `ge=1, le=22`.

- [ ] **Step 5: Add fields to `Roster`**

In the `Roster` model, add after `taxi`:

```python
    keepers: Optional[List[str]] = Field(default_factory=list, description="Kept player IDs")
    player_map: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Per-player metadata")
    co_owners: Optional[List[str]] = Field(default_factory=list, description="Co-owner user IDs")
```

- [ ] **Step 6: Delete unused trade models**

Remove the `TradeProposal`, `TradeAnalysis`, and `RosterAnalysis` classes (they are only referenced by `trade_tools.py`, which Task 11 deletes). Leave `MatchupScore` and `ErrorResponse`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (3 passed).

- [ ] **Step 8: Commit**

```bash
git add sleeper_mcp_server/models.py tests/test_models.py
git commit -m "fix: relax Matchup/PlayerStats validators, capture roster keepers; drop unused trade models"
```

---

## Task 5: Fix the player-stats endpoint in the client

**Files:**
- Modify: `sleeper_mcp_server/sleeper_client.py`
- Test: `tests/test_player_tools.py` (create, client portion)

**Interfaces:**
- Produces: `SleeperClient.get_player_stats(player_id, season, season_type="regular", week=None) -> dict` that fetches from `https://api.sleeper.com/stats/nfl/player/{player_id}` with query params, returning the raw stats payload (season totals dict, or `{week: payload}` when `week`/weekly requested). Adds a `base_url` override to `_make_request`.

> The current `get_player_stats(sport, season, ...)` is broken (omits `season` from the URL, expects `sport`). It is replaced entirely.

- [ ] **Step 1: Write the failing test**

Create `tests/test_player_tools.py`:

```python
import pytest
from unittest.mock import AsyncMock
from sleeper_mcp_server.sleeper_client import SleeperClient


@pytest.mark.asyncio
async def test_get_player_stats_hits_sleeper_com_with_season():
    client = SleeperClient()
    client._make_request = AsyncMock(return_value={"stats": {"pts_ppr": 300.0}})

    result = await client.get_player_stats("4046", "2025")
    await client.close()

    args, kwargs = client._make_request.await_args
    assert args[0] == "GET"
    assert args[1] == "/stats/nfl/player/4046"
    assert kwargs["params"]["season"] == "2025"
    assert kwargs["params"]["season_type"] == "regular"
    assert kwargs["base_url"] == "https://api.sleeper.com"
    assert result["stats"]["pts_ppr"] == 300.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_player_tools.py::test_get_player_stats_hits_sleeper_com_with_season -v`
Expected: FAIL — `_make_request` called with the old positional shape / no `base_url` kwarg.

- [ ] **Step 3: Add `base_url` override to `_make_request`**

In `sleeper_client.py`, change the `_make_request` signature and URL construction:

```python
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
```

And replace the URL line:

```python
        base = (base_url or self.base_url).rstrip("/")
        url = urljoin(base + "/", endpoint.lstrip("/"))
```

- [ ] **Step 4: Replace `get_player_stats`**

Replace the existing `get_player_stats` method body with:

```python
    async def get_player_stats(
        self,
        player_id: str,
        season: str,
        season_type: str = "regular",
        week: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get a single player's stats from api.sleeper.com.

        Returns season-total stats, or a {week: payload} map when week-
        grouping is requested. `week` filters the weekly map to one week.
        """
        params: Dict[str, Any] = {"season": season, "season_type": season_type}
        if week is not None:
            params["grouping"] = "week"
        data = await self._make_request(
            "GET", f"/stats/nfl/player/{player_id}",
            params=params, base_url="https://api.sleeper.com",
        )
        if week is not None and isinstance(data, dict):
            return data.get(str(week), {})
        return data or {}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_player_tools.py::test_get_player_stats_hits_sleeper_com_with_season -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sleeper_mcp_server/sleeper_client.py tests/test_player_tools.py
git commit -m "fix: correct get_player_stats endpoint (api.sleeper.com, season in query)"
```

---

## Task 6: Rewrite `player_tools.get_player_stats`

**Files:**
- Modify: `sleeper_mcp_server/tools/player_tools.py`
- Test: `tests/test_player_tools.py` (append)

**Interfaces:**
- Consumes: `SleeperClient.get_player_stats(player_id, season, season_type, week)` (Task 5); `SleeperClient.get_players` (existing).
- Produces: `PlayerTools.get_player_stats(player_id, season=None, week=None) -> dict` with keys `player_id`, `season`, `week`, `player_name`, `position`, `team`, `stats`. `season=None` is resolved by the caller (server) before calling; the tool treats `None` as "caller must pass a season".

- [ ] **Step 1: Write the failing test**

Append to `tests/test_player_tools.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from sleeper_mcp_server.tools.player_tools import PlayerTools
from sleeper_mcp_server.models import Player


def _player(**kw):
    base = dict(player_id="4046", full_name="Josh Allen", position="QB", team="BUF")
    base.update(kw)
    return Player.model_validate(base)


@pytest.mark.asyncio
async def test_player_tools_get_player_stats_shapes_result():
    client = MagicMock()
    client.get_player_stats = AsyncMock(return_value={"stats": {"pts_ppr": 300.0}})
    client.get_players = AsyncMock(return_value={"4046": _player()})
    cache = MagicMock()
    cache.get.return_value = None

    tools = PlayerTools(client, cache)
    result = await tools.get_player_stats("4046", season="2025")

    assert result["player_name"] == "Josh Allen"
    assert result["position"] == "QB"
    assert result["season"] == "2025"
    assert result["stats"] == {"pts_ppr": 300.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_player_tools.py::test_player_tools_get_player_stats_shapes_result -v`
Expected: FAIL — current method passes wrong args / mis-shapes `stats`.

- [ ] **Step 3: Rewrite the method**

In `player_tools.py`, replace `get_player_stats` with:

```python
    async def get_player_stats(
        self, player_id: str, season: str, week: Optional[int] = None
    ) -> dict[str, Any]:
        """Get a single player's statistics for a season (optionally one week)."""
        try:
            cache_key = f"player_stats:{player_id}:{season}:{week or 'season'}"
            cached = self.cache.get(cache_key, CacheDataType.PLAYER_DATA)
            if cached is not None:
                return cached

            raw = await self.client.get_player_stats(player_id, season, week=week)
            stats = raw.get("stats", raw) if isinstance(raw, dict) else {}

            all_players = await self.client.get_players("nfl")
            info = all_players.get(player_id)

            result = {
                "player_id": player_id,
                "season": season,
                "week": week,
                "player_name": info.full_name if info else "Unknown",
                "position": info.position if info else "Unknown",
                "team": info.team if info else "Unknown",
                "stats": stats,
            }
            self.cache.set(cache_key, result, CacheDataType.PLAYER_DATA, ttl_override=3600)
            return result
        except SleeperAPIError as e:
            logger.error(f"API error getting player stats: {e}")
            return {"error": f"Failed to retrieve player stats: {e}",
                    "retry_after": getattr(e, "retry_after", None)}
```

(Keep the existing `Optional` import; it is already imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_player_tools.py::test_player_tools_get_player_stats_shapes_result -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sleeper_mcp_server/tools/player_tools.py tests/test_player_tools.py
git commit -m "fix: rewrite player_tools.get_player_stats for correct endpoint and shape"
```

---

## Task 7: Client-level daily cache for the player catalog

**Files:**
- Modify: `sleeper_mcp_server/sleeper_client.py`
- Test: `tests/test_player_tools.py` (append)

**Interfaces:**
- Produces: `SleeperClient.get_players(sport="nfl")` memoizes the ~15 MB catalog in-process for 24h; repeat calls within the window do not re-fetch.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_player_tools.py`:

```python
@pytest.mark.asyncio
async def test_get_players_caches_within_day():
    client = SleeperClient()
    client._make_request = AsyncMock(return_value={"4046": {
        "player_id": "4046", "full_name": "Josh Allen", "position": "QB", "team": "BUF"}})

    first = await client.get_players("nfl")
    second = await client.get_players("nfl")
    await client.close()

    assert "4046" in first and "4046" in second
    client._make_request.assert_awaited_once()  # only one network fetch
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_player_tools.py::test_get_players_caches_within_day -v`
Expected: FAIL — `_make_request` awaited twice.

- [ ] **Step 3: Add in-process memoization**

In `SleeperClient.__init__`, add cache state:

```python
        self._players_cache: Dict[str, Dict[str, Player]] = {}
        self._players_cache_at: Dict[str, float] = {}
        self._players_ttl: float = 24 * 3600
```

In `get_players`, wrap the fetch:

```python
    async def get_players(self, sport: str = "nfl") -> Dict[str, Player]:
        now = time.time()
        if sport in self._players_cache and (now - self._players_cache_at.get(sport, 0)) < self._players_ttl:
            return self._players_cache[sport]

        data = await self._make_request("GET", f"/players/{sport}")
        if not data:
            return {}
        players = {}
        for player_id, player_data in data.items():
            try:
                players[player_id] = Player.model_validate(player_data)
            except ValidationError as e:
                logger.warning(f"Failed to validate player {player_id}: {e}")
                continue
        self._players_cache[sport] = players
        self._players_cache_at[sport] = now
        return players
```

(`time` is already imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_player_tools.py::test_get_players_caches_within_day -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sleeper_mcp_server/sleeper_client.py tests/test_player_tools.py
git commit -m "perf: cache the player catalog in-process for 24h"
```

---

## Task 8: FastMCP app skeleton, lifespan, and `get_nfl_state` tool

**Files:**
- Rewrite: `sleeper_mcp_server/server.py`
- Modify: `sleeper_mcp_server/__main__.py`
- Test: `tests/test_server_integration.py`

**Interfaces:**
- Consumes: `SleeperClient`, `CacheManager`, `LeagueTools`, `MatchupTools`, `PlayerTools`, `NflState`, `resolve_default_season`.
- Produces: module-level `mcp = FastMCP("sleeper-mcp-server", lifespan=...)`; an `AppContext` dataclass with `client`, `cache`, and the tool instances; a registered `get_nfl_state` tool. `__main__.main()` calls `mcp.run()`.

> This task replaces the entire 1,363-line `server.py`. Later tasks add the remaining tools to this new file.

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_integration.py`:

```python
import pytest
from unittest.mock import AsyncMock
from mcp.shared.memory import create_connected_server_and_client_session

import sleeper_mcp_server.server as srv
from sleeper_mcp_server.models import NflState


@pytest.mark.asyncio
async def test_get_nfl_state_tool_roundtrip(monkeypatch):
    async def fake_state(self, sport="nfl"):
        return NflState(season="2026", season_type="off", week=0,
                        display_week=1, previous_season="2025")
    monkeypatch.setattr("sleeper_mcp_server.sleeper_client.SleeperClient.get_nfl_state", fake_state)

    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert "get_nfl_state" in names

        res = await client.call_tool("get_nfl_state", {})
        assert res.structuredContent["season"] == "2026"
        assert res.structuredContent["season_type"] == "off"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server_integration.py::test_get_nfl_state_tool_roundtrip -v`
Expected: FAIL — `srv.mcp` does not exist (old server has no FastMCP app).

- [ ] **Step 3: Rewrite `server.py`**

Replace the entire contents of `sleeper_mcp_server/server.py` with:

```python
"""FastMCP server for the Sleeper Fantasy Football API."""

import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .sleeper_client import SleeperClient
from .cache import CacheManager
from .nfl_state import resolve_default_season
from .tools.league_tools import LeagueTools
from .tools.matchup_tools import MatchupTools
from .tools.player_tools import PlayerTools
from .models import NflState

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


@dataclass
class AppContext:
    client: SleeperClient
    cache: CacheManager
    league: LeagueTools
    player: PlayerTools
    matchup: MatchupTools


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    client = SleeperClient()
    cache = CacheManager()
    try:
        yield AppContext(
            client=client,
            cache=cache,
            league=LeagueTools(client, cache),
            player=PlayerTools(client, cache),
            matchup=MatchupTools(client, cache),
        )
    finally:
        await client.close()


mcp = FastMCP("sleeper-mcp-server", lifespan=lifespan)


def _ctx(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


async def _default_season(app: AppContext) -> str:
    return resolve_default_season(await app.client.get_nfl_state())


@mcp.tool(title="NFL State", annotations=READ_ONLY)
async def get_nfl_state(ctx: Context) -> NflState:
    """Get the current NFL season, week, and season type from Sleeper."""
    return await _ctx(ctx).client.get_nfl_state()
```

- [ ] **Step 4: Update `__main__.py`**

Replace `sleeper_mcp_server/__main__.py` with:

```python
"""Entry point for the Sleeper MCP server."""

import logging
import sys


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )
    from .server import mcp
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_server_integration.py::test_get_nfl_state_tool_roundtrip -v`
Expected: PASS.

> If the import path `mcp.shared.memory.create_connected_server_and_client_session` or the `res.structuredContent` access differs in the installed `mcp` version, confirm against `python -c "import mcp.shared.memory as m; print(dir(m))"` and adjust the test accordingly before proceeding.

- [ ] **Step 6: Commit**

```bash
git add sleeper_mcp_server/server.py sleeper_mcp_server/__main__.py tests/test_server_integration.py
git commit -m "feat: rewrite server as FastMCP app with lifespan and get_nfl_state"
```

---

## Task 9: Register league tools

**Files:**
- Modify: `sleeper_mcp_server/server.py`
- Test: `tests/test_server_integration.py` (append)

**Interfaces:**
- Consumes: `LeagueTools` methods (existing): `get_user_leagues(username, season)`, `get_league_info(league_id)`, `get_league_rosters(league_id)`, `get_league_rosters_with_draft_info(league_id)`, `get_league_users(league_id)`, `get_roster_user_mapping(league_id)`, `get_league_draft(league_id)`.
- Produces: 7 registered league tools returning `dict` (structured content). `get_user_leagues` resolves season when not given.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server_integration.py`:

```python
@pytest.mark.asyncio
async def test_get_user_leagues_resolves_season(monkeypatch):
    async def fake_state(self, sport="nfl"):
        return NflState(season="2026", season_type="off", week=0,
                        display_week=1, previous_season="2025")
    captured = {}
    async def fake_get_user_leagues(self, username, season):
        captured["season"] = season
        return {"username": username, "season": season, "leagues": []}
    monkeypatch.setattr("sleeper_mcp_server.sleeper_client.SleeperClient.get_nfl_state", fake_state)
    monkeypatch.setattr("sleeper_mcp_server.tools.league_tools.LeagueTools.get_user_leagues", fake_get_user_leagues)

    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert "get_user_leagues" in names
        await client.call_tool("get_user_leagues", {"username": "sourknives"})
        assert captured["season"] == "2025"  # offseason fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server_integration.py::test_get_user_leagues_resolves_season -v`
Expected: FAIL — tool `get_user_leagues` not registered.

- [ ] **Step 3: Add the league tools to `server.py`**

Append to `sleeper_mcp_server/server.py`:

```python
@mcp.tool(title="User Leagues", annotations=READ_ONLY)
async def get_user_leagues(username: str, ctx: Context, season: Optional[str] = None) -> dict[str, Any]:
    """Get all NFL leagues for a Sleeper username. Defaults to the current season."""
    app = _ctx(ctx)
    season = season or await _default_season(app)
    return await app.league.get_user_leagues(username=username, season=season)


@mcp.tool(title="League Info", annotations=READ_ONLY)
async def get_league_info(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get detailed information about a specific league."""
    return await _ctx(ctx).league.get_league_info(league_id=league_id)


@mcp.tool(title="League Rosters", annotations=READ_ONLY)
async def get_league_rosters(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get all team rosters in a league."""
    return await _ctx(ctx).league.get_league_rosters(league_id=league_id)


@mcp.tool(title="League Rosters with Draft Info", annotations=READ_ONLY)
async def get_league_rosters_with_draft_info(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get all rosters with draft-position metadata per player."""
    return await _ctx(ctx).league.get_league_rosters_with_draft_info(league_id=league_id)


@mcp.tool(title="League Users", annotations=READ_ONLY)
async def get_league_users(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get all users/participants in a league."""
    return await _ctx(ctx).league.get_league_users(league_id=league_id)


@mcp.tool(title="Roster-User Mapping", annotations=READ_ONLY)
async def get_roster_user_mapping(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get a mapping of roster IDs to user names for a league."""
    return await _ctx(ctx).league.get_roster_user_mapping(league_id=league_id)


@mcp.tool(title="League Draft", annotations=READ_ONLY)
async def get_league_draft(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get draft results and pick information for a league."""
    return await _ctx(ctx).league.get_league_draft(league_id=league_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server_integration.py::test_get_user_leagues_resolves_season -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sleeper_mcp_server/server.py tests/test_server_integration.py
git commit -m "feat: register league tools on FastMCP with season resolution"
```

---

## Task 10: Register player and matchup tools

**Files:**
- Modify: `sleeper_mcp_server/server.py`
- Test: `tests/test_server_integration.py` (append)

**Interfaces:**
- Consumes: `PlayerTools.search_players(query, position)`, `PlayerTools.get_trending_players(sport, add_drop)`, `PlayerTools.get_player_stats(player_id, season, week)`; `MatchupTools.get_matchups(league_id, week)`, `MatchupTools.get_matchup_scores(league_id, week)`.
- Produces: 5 registered tools. `get_player_stats` resolves season when not given. `position`/`add_drop` typed with `Literal`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server_integration.py`:

```python
@pytest.mark.asyncio
async def test_player_and_matchup_tools_registered(monkeypatch):
    async def fake_state(self, sport="nfl"):
        return NflState(season="2026", season_type="regular", week=1,
                        display_week=1, previous_season="2025")
    monkeypatch.setattr("sleeper_mcp_server.sleeper_client.SleeperClient.get_nfl_state", fake_state)

    async def fake_stats(self, player_id, season, week=None):
        return {"player_id": player_id, "season": season, "stats": {"pts_ppr": 1.0}}
    monkeypatch.setattr("sleeper_mcp_server.tools.player_tools.PlayerTools.get_player_stats", fake_stats)

    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert {"search_players", "get_trending_players", "get_player_stats",
                "get_matchups", "get_matchup_scores"} <= names
        res = await client.call_tool("get_player_stats", {"player_id": "4046"})
        assert res.structuredContent["season"] == "2026"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server_integration.py::test_player_and_matchup_tools_registered -v`
Expected: FAIL — those tools not registered.

- [ ] **Step 3: Add the tools to `server.py`**

(`Literal` and `Any` are already imported in the typing line from Task 8.) Append:

```python
@mcp.tool(title="Search Players", annotations=READ_ONLY)
async def search_players(
    query: str, ctx: Context,
    position: Optional[Literal["QB", "RB", "WR", "TE", "K", "DEF"]] = None,
) -> dict[str, Any]:
    """Search for players by name, with optional position filter."""
    return await _ctx(ctx).player.search_players(query=query, position=position)


@mcp.tool(title="Trending Players", annotations=READ_ONLY)
async def get_trending_players(
    ctx: Context,
    add_drop: Literal["add", "drop"] = "add",
    sport: str = "nfl",
) -> dict[str, Any]:
    """Get trending players (most added or dropped)."""
    return await _ctx(ctx).player.get_trending_players(sport=sport, add_drop=add_drop)


@mcp.tool(title="Player Stats", annotations=READ_ONLY)
async def get_player_stats(
    player_id: str, ctx: Context,
    season: Optional[str] = None, week: Optional[int] = None,
) -> dict[str, Any]:
    """Get a player's stats for a season (optionally one week)."""
    app = _ctx(ctx)
    season = season or await _default_season(app)
    return await app.player.get_player_stats(player_id=player_id, season=season, week=week)


@mcp.tool(title="Matchups", annotations=READ_ONLY)
async def get_matchups(league_id: str, week: int, ctx: Context) -> dict[str, Any]:
    """Get matchups for a specific week in a league."""
    return await _ctx(ctx).matchup.get_matchups(league_id=league_id, week=week)


@mcp.tool(title="Matchup Scores", annotations=READ_ONLY)
async def get_matchup_scores(league_id: str, week: int, ctx: Context) -> dict[str, Any]:
    """Get real-time scoring for matchups in a specific week."""
    return await _ctx(ctx).matchup.get_matchup_scores(league_id=league_id, week=week)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server_integration.py::test_player_and_matchup_tools_registered -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sleeper_mcp_server/server.py tests/test_server_integration.py
git commit -m "feat: register player and matchup tools on FastMCP"
```

---

## Task 11: Remove trade tools and dead code

**Files:**
- Delete: `sleeper_mcp_server/tools/trade_tools.py`
- Modify: `sleeper_mcp_server/server.py` (ensure no trade imports remain)
- Test: `tests/test_server_integration.py` (append)

**Interfaces:**
- Produces: a server with exactly 13 tools and no references to `TradeTools`/trade models.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server_integration.py`:

```python
@pytest.mark.asyncio
async def test_tool_inventory_is_thirteen_and_no_trade_tools():
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert "analyze_trade_targets" not in names
    assert "evaluate_roster_needs" not in names
    assert len(names) == 13
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/test_server_integration.py::test_tool_inventory_is_thirteen_and_no_trade_tools -v`
Expected: PASS if Tasks 8–10 are complete and no trade tools were ever added to the new server. (The new `server.py` never imported `TradeTools`, so this is mostly a guard.) If it fails on count, reconcile against the 13 expected names.

- [ ] **Step 3: Delete the file and confirm no references**

```bash
git rm sleeper_mcp_server/tools/trade_tools.py
grep -rn "trade_tools\|TradeTools\|TradeAnalysis\|TradeProposal\|RosterAnalysis" sleeper_mcp_server/ || echo "no references"
```
Expected: `no references`.

- [ ] **Step 4: Run the whole suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove cosmetic trade tools and dead trade code"
```

---

## Task 12: Update README and Claude Desktop config docs

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: docs matching the refreshed server (13 tools, no trade tools, dynamic season, ≥3.10, structured output).

- [ ] **Step 1: Update the tool list and notes**

In `README.md`:
- Remove the `analyze_trade_targets` and `evaluate_roster_needs` sections.
- Add a `get_nfl_state` entry under a new "State Tools" heading.
- In `get_player_stats`, note `season` defaults to the current season and an optional `week` parameter exists.
- Remove the hardcoded `"2024"` defaults from every "Parameters" block; replace with "defaults to current season".
- Update Prerequisites to "Python 3.10 or higher".
- In the `autoApprove` config examples, drop the two trade tools and add `get_nfl_state`.

- [ ] **Step 2: Verify no stale references remain**

Run:
```bash
grep -n "2024\|analyze_trade_targets\|evaluate_roster_needs\|3.8" README.md || echo "clean"
```
Expected: `clean` (or only intentional historical mentions).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for refreshed tool surface and dynamic season"
```

---

## Final Verification

- [ ] Run the full suite: `pytest -q` — all pass.
- [ ] Smoke-start the server: `python -m sleeper_mcp_server` starts without error (Ctrl-C to stop); logs go to stderr only.
- [ ] Live sanity check (network): with the server configured in Claude Desktop, "what NFL week is it?" calls `get_nfl_state`, and "show my Sleeper leagues for sourknives" returns the 2025 leagues (offseason fallback) rather than 2024.

---

## Self-Review

**1. Spec coverage:**
- §2 decisions → Tasks 1 (packaging), 8 (FastMCP), 11 (remove trade), 8–10 (structured output via dict/model returns + `get_nfl_state`). ✓
- §4.1 season resolver + offseason fallback → Tasks 2, 3, 9, 10. ✓
- §4.2 `get_player_stats` rewrite → Tasks 5, 6. ✓
- §4.3 player-catalog caching → Task 7. ✓
- §4.4 model relaxation + drop trade models → Task 4. ✓
- §4.5 packaging → Task 1. ✓
- §5 tool surface (13 tools) → Tasks 8–11 (+ count guard). ✓
- §6 testing (in-memory client) → Tasks 8–11 integration tests. ✓

**2. Placeholder scan:** No TBD/TODO; every code step has complete code; the one SDK-API uncertainty (in-memory session import) is called out with an explicit verification command, not left vague.

**3. Type consistency:** `get_player_stats` is `(player_id, season, week)` in the client (Task 5), `player_tools` (Task 6), and the server tool (Task 10). `resolve_default_season(state)` signature matches across Tasks 3, 8. `AppContext` fields (`client`, `cache`, `league`, `player`, `matchup`) are defined in Task 8 and used in 9–10. `NflState` fields consistent across Tasks 2, 3, 8.
