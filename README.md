# Sleeper MCP Server

A Model Context Protocol (MCP) server that provides Claude Desktop with access to Sleeper Fantasy Football API data. This server enables users to query league information, player data, matchups, draft results, and perform trade analysis through natural language interactions with Claude.

## Features

- **League Management**: Query leagues, rosters, users, and league settings
- **Draft Analysis**: Complete draft results with pick positions, keeper status, and team attribution
  - Full draft history with all rounds and picks
  - Player draft metadata showing original draft position and team
  - Keeper identification with 🔒 indicators
  - Free agent tracking for undrafted players
- **Player Information**: Search players, get statistics, and trending data
- **Matchup Analysis**: View current and historical matchups with real-time scoring
- **Trade Analysis**: Analyze potential trade targets and evaluate roster needs
- **Intelligent Caching**: Optimized API usage with TTL-based caching
- **Rate Limiting**: Respects Sleeper API limits with exponential backoff

## Installation

### Prerequisites

- Python 3.8 or higher
- Claude Desktop application

### Install from Source

1. Clone the repository:
```bash
git clone <repository-url>
cd sleeper-mcp-server
```

2. Install the package:
```bash
pip install -e .
```

3. For development with testing and linting tools:
```bash
pip install -e ".[dev]"
```



## Configuration

### Claude Desktop MCP Configuration

Add the following configuration to your Claude Desktop MCP settings file:

**Location of config file:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

**Basic Configuration:**
```json
{
  "mcpServers": {
    "sleeper": {
      "command": "python",
      "args": ["-m", "sleeper_mcp_server"],
      "env": {
        "LOG_LEVEL": "INFO"
      },
      "disabled": false,
      "autoApprove": [
        "get_user_leagues",
        "get_league_info",
        "search_players",
        "get_trending_players"
      ]
    }
  }
}
```

**Advanced Configuration with Custom Settings:**
```json
{
  "mcpServers": {
    "sleeper": {
      "command": "python",
      "args": ["-m", "sleeper_mcp_server"],
      "env": {
        "SLEEPER_API_BASE_URL": "https://api.sleeper.app/v1",
        "CACHE_TTL_SECONDS": "3600",
        "LOG_LEVEL": "INFO",
        "MAX_RETRIES": "3"
      },
      "disabled": false,
      "autoApprove": [
        "get_user_leagues",
        "get_league_info",
        "get_league_rosters",
        "get_league_rosters_with_draft_info",
        "get_league_users",
        "get_roster_user_mapping",
        "get_league_draft",
        "search_players",
        "get_trending_players",
        "get_player_stats",
        "get_matchups",
        "get_matchup_scores"
      ]
    }
  }
}
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SLEEPER_API_BASE_URL` | Sleeper API endpoint | `https://api.sleeper.app/v1` |
| `CACHE_TTL_SECONDS` | Default cache TTL in seconds | `3600` |
| `LOG_LEVEL` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `MAX_RETRIES` | Maximum API retry attempts | `3` |

## Available MCP Tools

### League Tools

#### `get_user_leagues`
Get all leagues for a username in a specific season.

**Parameters:**
- `username` (required): Sleeper username to look up
- `season` (optional): Season year (default: "2024")

**Example Usage:**
```
Show me all leagues for username "john_doe" in 2024
```

#### `get_league_info`
Get detailed information about a specific league.

**Parameters:**
- `league_id` (required): League ID to retrieve information for

**Example Usage:**
```
Get information for league ID "123456789"
```

#### `get_league_rosters`
Get all team rosters in a league.

**Parameters:**
- `league_id` (required): League ID to retrieve rosters for

**Example Usage:**
```
Show me all rosters in league "123456789"
```

#### `get_league_users`
Get all users/participants in a league.

**Parameters:**
- `league_id` (required): League ID to retrieve users for

**Example Usage:**
```
Who are the users in league "123456789"?
```

#### `get_league_rosters_with_draft_info`
Get all team rosters in a league with complete draft position metadata for each player.

**Parameters:**
- `league_id` (required): League ID to retrieve rosters for

**Example Usage:**
```
Show me all rosters with draft information for league "123456789"
```

#### `get_roster_user_mapping`
Get a clear mapping of roster IDs to user names for a league.

**Parameters:**
- `league_id` (required): League ID to get roster-user mapping for

**Example Usage:**
```
Show me the roster to user mapping for league "123456789"
```

#### `get_league_draft`
Get complete draft results and pick information for a league.

**Parameters:**
- `league_id` (required): League ID to get draft information for

**Example Usage:**
```
Show me the draft results for league "123456789"
```

### Player Tools

#### `search_players`
Search for players by name with optional position filtering.

**Parameters:**
- `query` (required): Player name or partial name to search for
- `position` (optional): Position filter (QB, RB, WR, TE, K, DEF)

**Example Usage:**
```
Search for players named "Josh Allen"
Find all quarterbacks with "Josh" in their name
```

#### `get_trending_players`
Get trending players (most added/dropped).

**Parameters:**
- `sport` (optional): Sport type (default: "nfl")
- `add_drop` (optional): Type of trend - "add" or "drop" (default: "add")

**Example Usage:**
```
Show me the most added players this week
What players are being dropped the most?
```

#### `get_player_stats`
Get player statistics for a specific season.

**Parameters:**
- `player_id` (required): Player ID to get stats for
- `season` (optional): Season year (default: "2024")

**Example Usage:**
```
Get stats for player ID "4046" in 2024
```

### Matchup Tools

#### `get_matchups`
Get matchups for a specific week in a league.

**Parameters:**
- `league_id` (required): League ID to retrieve matchups for
- `week` (required): Week number (1-22)

**Example Usage:**
```
Show me week 5 matchups for league "123456789"
```

#### `get_matchup_scores`
Get real-time scoring information for matchups in a specific week.

**Parameters:**
- `league_id` (required): League ID to retrieve scores for
- `week` (required): Week number (1-22)

**Example Usage:**
```
What are the current scores for week 8 in league "123456789"?
```

### Trade Tools

#### `analyze_trade_targets`
Analyze potential trade targets for a roster based on positional needs.

**Parameters:**
- `league_id` (required): League ID to analyze
- `roster_id` (required): Roster ID requesting trade analysis
- `position` (optional): Position to focus analysis on (QB, RB, WR, TE, K, DEF)

**Example Usage:**
```
Analyze trade targets for roster 3 in league "123456789"
Find running back trade targets for my roster
```

#### `evaluate_roster_needs`
Evaluate roster strengths and weaknesses across all positions.

**Parameters:**
- `league_id` (required): League ID to analyze
- `roster_id` (required): Roster ID to evaluate

**Example Usage:**
```
Evaluate the strengths and weaknesses of roster 1 in league "123456789"
```

## API Rate Limiting and Caching

### Rate Limiting

The server implements intelligent rate limiting to respect Sleeper API guidelines:

- **Rate Limit**: Follows Sleeper's documented rate limits
- **Retry Logic**: Exponential backoff (1s, 2s, 4s, 8s) for rate-limited requests
- **Queue Management**: Requests are queued during rate limit periods
- **User Feedback**: Clear messages when rate limits are encountered

### Caching Strategy

Different data types have optimized cache TTL values:

| Data Type | Cache TTL | Reason |
|-----------|-----------|---------|
| Player Data | 1 hour | Relatively static during season |
| League Settings | 24 hours | Rarely change mid-season |
| Draft Data | 24 hours | Historical data, doesn't change |
| Matchup Data (active) | 5 minutes | Real-time scoring updates |
| Matchup Data (completed) | 1 hour | Historical data is stable |
| Trending Players | 30 minutes | Updated frequently |
| Roster Data | 15 minutes | Changes with transactions |
| Roster Data (with draft) | 15 minutes | Changes with transactions |

**Cache Features:**
- In-memory caching for optimal performance
- TTL-based expiration
- Automatic cache invalidation
- Cache hit/miss logging for monitoring

## Usage Examples

### Basic League Queries

```
# Get your leagues
"Show me all leagues for username 'myusername'"

# Get league details
"What are the settings for league ID '123456789'?"

# View rosters
"Show me all the rosters in my main league"

# View rosters with draft information
"Show me all rosters with draft info - I want to see where each player was drafted and by whom"
```

### Player Research

```
# Search for players
"Find all players named 'Cooper'"

# Get trending players
"What players are being added the most this week?"

# Player statistics
"Show me Josh Allen's stats for 2024"
```

### Matchup Analysis

```
# Current week matchups
"What are this week's matchups in my league?"

# Live scoring
"What are the current scores for week 8?"

# Historical data
"Show me the results from week 3"
```

### Draft Analysis

```
# Complete draft results
"Show me the draft results for my league"

# Roster with draft info
"Show me all rosters with draft information - I want to see where each player was drafted"

# Keeper analysis
"Which players were kept from last year and what was their original draft cost?"

# Draft value analysis
"Show me players who are outperforming their draft position"
```

### Trade Analysis

```
# Find trade partners
"Who should I target for a trade in my league? I need a running back"

# Roster evaluation
"Analyze my roster strengths and weaknesses"

# Specific position analysis
"Find quarterback trade targets for my team"
```

## Troubleshooting

### Common Issues

#### 1. Server Won't Start

**Symptoms:**
- Claude Desktop shows "Server unavailable" error
- No response from MCP tools

**Solutions:**
- Verify Python installation: `python --version` (should be 3.8+)
- Check package installation: `pip show sleeper-mcp-server`
- Verify Claude Desktop configuration syntax
- Check logs for specific error messages

#### 2. Authentication/API Errors

**Symptoms:**
- "API request failed" errors
- "Invalid league ID" messages

**Solutions:**
- Verify league IDs are correct (18-character strings)
- Check username spelling and case sensitivity
- Ensure Sleeper API is accessible from your network
- Try again after a few minutes (may be temporary API issues)

#### 3. Rate Limiting Issues

**Symptoms:**
- "Rate limit exceeded" messages
- Slow response times
- "Please wait" messages

**Solutions:**
- Wait for the specified retry period
- Reduce frequency of requests
- Use cached data when possible
- Check if multiple instances are running

#### 4. Cache Issues

**Symptoms:**
- Stale data being returned
- Inconsistent results

**Solutions:**
- Restart the MCP server to clear cache
- Adjust `CACHE_TTL_SECONDS` environment variable
- Check system memory availability

#### 5. Configuration Problems

**Symptoms:**
- Tools not appearing in Claude Desktop
- Environment variables not working

**Solutions:**
- Validate JSON syntax in Claude Desktop config
- Restart Claude Desktop after configuration changes
- Check file permissions on config file
- Verify environment variable names and values

### Debug Mode

Enable debug logging for detailed troubleshooting:

```json
{
  "mcpServers": {
    "sleeper": {
      "command": "python",
      "args": ["-m", "sleeper_mcp_server"],
      "env": {
        "LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

### Getting Help

1. **Check Logs**: Enable DEBUG logging to see detailed error information
2. **Verify Configuration**: Ensure Claude Desktop MCP configuration is correct
3. **Test API Access**: Verify you can access Sleeper API directly
4. **Update Dependencies**: Ensure all packages are up to date
5. **Restart Services**: Try restarting both the MCP server and Claude Desktop

### Performance Optimization

#### For Large Leagues
- Use position filtering in player searches
- Cache frequently accessed league data
- Limit historical matchup queries

#### For Multiple Leagues
- Batch similar requests when possible
- Use appropriate cache TTL settings
- Monitor rate limit usage

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=sleeper_mcp_server

# Run specific test file
pytest tests/test_server.py
```

### Code Quality

```bash
# Format code
black sleeper_mcp_server/

# Sort imports
isort sleeper_mcp_server/

# Lint code
flake8 sleeper_mcp_server/

# Type checking
mypy sleeper_mcp_server/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Sleeper API](https://docs.sleeper.app/) for providing comprehensive fantasy football data including detailed draft information
- [Model Context Protocol](https://modelcontextprotocol.io/) for the MCP framework
- [Claude Desktop](https://claude.ai/desktop) for MCP integration

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review existing GitHub issues
3. Create a new issue with detailed information about your problem

---

**Note**: This MCP server is not officially affiliated with Sleeper. It's a third-party integration that uses Sleeper's public API.