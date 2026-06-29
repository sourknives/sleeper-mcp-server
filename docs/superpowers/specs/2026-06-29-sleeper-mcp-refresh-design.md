# Sleeper MCP Server — Refresh Design (Phase 1)

**Date:** 2026-06-29
**Status:** Approved (design); pending spec review → implementation plan
**Scope:** Phase 1 only — make every tool accurate and migrate to a modern FastMCP foundation. New analytics tools and Claude skills are Phase 2 (previewed at the end).

---

## 1. Context & motivation

The server was built ~2025 with Kiro's spec-driven workflow and has drifted over a year. A verification pass (live Sleeper API + direct code audit) found that several tools return wrong, stale, or empty data, and the implementation predates every MCP SDK feature since 1.0.

This document captures the agreed design to refresh it. The destination is also strategic: Phase 2 will layer fantasy-football "success" skills (projections, waivers, start/sit, trade evaluation) on top of an accurate, modern server.

### Verified findings (with evidence)

| Severity | Finding | Evidence |
|----------|---------|----------|
| Critical | `get_player_stats` is dead — the tool passes `player_id` into the client's `sport` param, and the client never puts `season` in the URL | `player_tools.py:201`, `sleeper_client.py:452`; built path `/v1/stats/nfl/regular` returns **HTTP 404** live |
| High | Season defaults hardcoded to `"2024"` (now 2026) — "my leagues"/stats silently target a 2-season-old year | `server.py:111`, `player_tools.py:182`, `league_tools.py:33`; live `/state/nfl` → `season:"2026"`. For `sourknives`: 2024=7 leagues, 2025=5, 2026=0 |
| High | Trade tools (`analyze_trade_targets`, `evaluate_roster_needs`) are cosmetic — "strength" = `players ÷ starter_slots`, "value" = a constant position weight, proposals name no players | `trade_tools.py:307`, `:547` |
| Medium | The ~15 MB `/players/nfl` catalog is re-downloaded on every search/trending/stats call (no client-level cache) | `player_tools.py:51`, `:140`, `:205` |
| Medium | Over-strict models reject real data — `Matchup` **raises** if `starters ⊄ players` | `models.py:219` |
| Low | Package can't install — `requires-python ">=3.8"` but `mcp` needs ≥3.10 | `pyproject.toml:10` |

### Correction to the auto-report
An automated synthesis labeled **projections** as an external dependency. This is **wrong** — projections are Sleeper-native and rich, verified live:
- `/projections/nfl/{season}/{week}` → ~9,395 players with `pts_ppr` / `pts_half_ppr` / `pts_std` + ADP.
- Per-player weekly stats *and* projections at `api.sleeper.com/{stats|projections}/nfl/player/{id}?grouping=week`.

This unlocks start/sit, waivers, and matchup previews on native data in Phase 2 (no scraping). It does not change Phase 1 scope but informs it (the `get_player_stats` rewrite uses the same host/shape).

### What is confirmed good and stays
HTTP robustness (429 + `Retry-After`, exponential backoff on 5xx/timeouts, client-side rate limiting); correct v1 endpoint paths; Pydantic v2 models; stdio transport with stderr-only logging; draft/keeper enrichment (`get_league_rosters_with_draft_info`, `get_roster_user_mapping`).

---

## 2. Decisions

1. **Language/foundation:** stay **Python**, migrate the low-level `mcp.server.Server` API → **FastMCP**. Rationale: the pain is SDK-version + logic drift, not the language; Phase 2 is analytics-heavy where Python's ecosystem (nflverse, pandas, scipy/PuLP) is the moat.
2. **Sequencing:** **modernize + fix in one pass** (not fix-first-migrate-later, not clean rebuild).
3. **Trade tools:** **remove** `analyze_trade_targets` and `evaluate_roster_needs` (and their unused models). Rebuild properly in Phase 2 on real projections/values.
4. **Output:** switch to **structured output** (return Pydantic models → FastMCP auto `outputSchema` + `structuredContent`); delete the ~775 lines of `_format_*` markdown. Claude formats for the user.
5. **`get_nfl_state`:** expose as a real read-only tool (in addition to using it internally for season defaults).

---

## 3. Architecture

Keep the layered package (`client → cache → models → tools`). Changes concentrate in the server layer.

```
sleeper_mcp_server/
  __main__.py        # entry (unchanged behavior)
  server.py          # REWRITE: FastMCP app, @mcp.tool() per function, lifespan
  sleeper_client.py  # KEEP + fix stats endpoint + client-level player-cache hook
  nfl_state.py       # NEW: season/week resolution (+ offseason fallback)
  cache.py           # KEEP (used by lifespan; add player-catalog daily cache)
  models.py          # KEEP + relax validators; drop unused trade models
  tools/
    league_tools.py  # KEEP (season default via resolver)
    player_tools.py  # KEEP + fix get_player_stats, shared player cache
    matchup_tools.py # KEEP
    # trade_tools.py DELETED
```

- **FastMCP app.** `mcp = FastMCP("sleeper-mcp-server")`; one `@mcp.tool()` per function delegating to the existing tool classes. Type hints → input schema; `Literal[...]` → enums; docstrings → descriptions. Removes `_list_tools` (~260 lines), `_route_tool_call` (~85), all 14 `inputSchema` dicts, and all `_format_*` methods (~775).
- **Lifespan + Context.** `@asynccontextmanager` builds the `httpx` client + `CacheManager` at startup and **closes the client at shutdown** (today it's never closed; init is a lazy race). Tools receive them via `Context`.
- **Annotations.** Every tool gets `readOnlyHint=True` (all are GETs) and a human `title`.
- **Transport.** Keep stdio + stderr logging (correct for local Claude Desktop).

---

## 4. Correctness fixes (detail)

### 4.1 Season/week resolution (`nfl_state.py`)
- `get_nfl_state()` → fetch `/state/nfl`, cache ~1h. Fields: `season`, `week`, `display_week`, `season_type`, `previous_season`.
- `resolve_default_season(user_id=None)`:
  - Base default = `state.season`.
  - **Offseason fallback:** if `season_type == "off"` *or* (when a `user_id` is given) the calendar season returns 0 leagues, use the most-recent season that has leagues (e.g., `previous_season`). This prevents the empty-2026 problem.
- Replace **all** hardcoded `"2024"` with the resolver. Tools still accept an explicit `season` to override.

### 4.2 `get_player_stats` rewrite
- Endpoint: `https://api.sleeper.com/stats/nfl/player/{player_id}?season_type=regular&season={season}` (+ `&grouping=week` when a `week`/weekly view is requested).
- Signature: `get_player_stats(player_id, season=<resolved>, week=None, season_type="regular")`.
- Returns a structured stat object (season totals, or a week→stats map). Remove the "treat league dict as one player" mishandling.

### 4.3 Player-catalog caching
- Fetch `/players/nfl` (~15 MB) **at most once/day**, cached at the **client level** and shared by search/trending/stats (today each call re-fetches, some twice).
- Optionally persist the catalog to disk (e.g., under a cache dir) so a server restart doesn't re-download. TTL ≈ 24h per Sleeper guidance.

### 4.4 Model relaxation (`models.py`)
- `Matchup`: starters-not-subset → **log warning, do not raise** (match `Roster`'s lenient behavior; real mid-week drops can violate it).
- `PlayerStats`: allow empty `stats` (return empties rather than erroring).
- `Roster`: capture `keepers` and `player_map` (currently dropped) for downstream use; keep ignoring other extras.
- Widen `Player.age` / position validators so unusual-but-valid players don't warn-spam.
- Delete unused `TradeAnalysis`, `TradeProposal`, `RosterAnalysis`.

### 4.5 Packaging (`pyproject.toml`)
- `requires-python = ">=3.10"`; drop 3.8/3.9 classifiers; retarget `black`/`mypy` to py310.
- Pin `mcp>=1.28,<2.0` (avoid the breaking 2.0 line).

---

## 5. Tool surface after refresh

**13 tools** (was 14: −2 trade, +1 state), all `readOnlyHint=True`:

| Group | Tools |
|-------|-------|
| League (7) | `get_user_leagues`, `get_league_info`, `get_league_rosters`, `get_league_rosters_with_draft_info`, `get_league_users`, `get_roster_user_mapping`, `get_league_draft` |
| Player (3) | `search_players`, `get_trending_players`, `get_player_stats` *(fixed)* |
| Matchup (2) | `get_matchups`, `get_matchup_scores` |
| State (1) | `get_nfl_state` *(new)* |
| Removed | ~~`analyze_trade_targets`~~, ~~`evaluate_roster_needs`~~ |

Each tool returns its Pydantic model(s) as structured output.

---

## 6. Testing

`tests/` currently holds only `__init__.py`, so the coverage gates are vacuous. Add real tests driving tools through the **in-memory MCP client** with a **mocked `SleeperClient`** injected via the lifespan:

- `get_player_stats` hits the corrected endpoint and shapes output correctly (regression for the critical bug).
- Season resolver returns the current season in-season and the **offseason fallback** when the calendar season is empty.
- `Matchup` with `starters ⊄ players` **does not raise**.
- Structured-output schemas match the models for a representative tool in each group.
- Player-catalog cache is fetched once across multiple player calls.

---

## 7. Out of scope (Phase 2 preview)

Projections tool; waiver/FAAB recommender; start-sit / optimal-lineup optimizer; standings & playoff-odds; transactions feed; a real trade evaluator (projections + external values like FantasyCalc); and the Claude **skills** that orchestrate these — including **multi-league handling** for `sourknives`'s 7-league, multi-format setup (12-team redraft, 18-team Guillotine, best-ball, keepers).

---

## 8. Open questions

None blocking. Disk-persistence of the player catalog (4.3) is a nice-to-have that can be decided during implementation.
