"""
Pydantic models for Sleeper API responses.

This module contains data models that represent the structure of responses
from the Sleeper Fantasy Football API, with validation and serialization logic.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class LeagueStatus(str, Enum):
    """Enum for league status values."""
    PRE_DRAFT = "pre_draft"
    DRAFTING = "drafting"
    IN_SEASON = "in_season"
    COMPLETE = "complete"


class PlayerStatus(str, Enum):
    """Enum for player status values."""
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    INJURED_RESERVE = "Injured Reserve"
    NON_FOOTBALL_INJURY = "Non Football Injury"
    PHYSICALLY_UNABLE_TO_PERFORM = "Physically Unable to Perform"
    PRACTICE_SQUAD = "Practice Squad"
    SUSPENDED = "Suspended"


class LeagueSettings(BaseModel):
    """Model for league settings configuration."""
    num_teams: int = Field(..., ge=2, le=32, description="Number of teams in league")
    playoff_teams: int = Field(..., ge=2, description="Number of playoff teams")
    playoff_weeks: Optional[List[int]] = Field(None, description="Weeks for playoffs")
    playoff_round_type: int = Field(default=0, description="Playoff round type")
    playoff_seed_type: int = Field(default=0, description="Playoff seeding type")
    daily_waivers: int = Field(default=0, description="Daily waivers setting")
    waiver_type: int = Field(default=0, description="Waiver wire type")
    waiver_clear_days: int = Field(default=1, description="Days for waiver clearance")
    daily_waivers_last_ran: Optional[int] = Field(None, description="Last waiver run timestamp")
    reserve_slots: int = Field(default=0, ge=0, description="Number of reserve slots")
    taxi_slots: int = Field(default=0, ge=0, description="Number of taxi squad slots")
    bench_lock: int = Field(default=0, description="Bench lock setting")


class League(BaseModel):
    """Model for Sleeper league information."""
    league_id: str = Field(..., description="Unique league identifier")
    name: str = Field(..., min_length=1, max_length=100, description="League name")
    season: str = Field(..., pattern=r"^\d{4}$", description="Season year")
    season_type: str = Field(default="regular", description="Season type")
    status: LeagueStatus = Field(..., description="Current league status")
    sport: str = Field(default="nfl", description="Sport type")
    settings: LeagueSettings = Field(..., description="League settings")
    scoring_settings: Dict[str, Union[int, float]] = Field(
        default_factory=dict, description="Scoring configuration"
    )
    roster_positions: List[str] = Field(..., description="Available roster positions")
    total_rosters: int = Field(..., ge=2, le=32, description="Total number of rosters")
    draft_id: Optional[str] = Field(None, description="Draft identifier if applicable")
    avatar: Optional[str] = Field(None, description="League avatar URL")
    
    @field_validator('roster_positions')
    @classmethod
    def validate_roster_positions(cls, v):
        """Validate that roster positions are not empty."""
        if not v:
            raise ValueError("Roster positions cannot be empty")
        return v


class User(BaseModel):
    """Model for Sleeper user information."""
    user_id: str = Field(..., description="Unique user identifier")
    username: Optional[str] = Field(None, min_length=1, max_length=50, description="Username")
    display_name: str = Field(..., min_length=1, max_length=100, description="Display name")
    avatar: Optional[str] = Field(None, description="User avatar URL")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional user data")
    is_owner: Optional[bool] = Field(None, description="Whether user is league owner")
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        """Validate username format."""
        if v is not None and not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Username must contain only alphanumeric characters, underscores, and hyphens")
        return v


class Player(BaseModel):
    """Model for Sleeper player information."""
    player_id: str = Field(..., description="Unique player identifier")
    full_name: str = Field(..., min_length=1, description="Player's full name")
    first_name: Optional[str] = Field(None, description="Player's first name")
    last_name: Optional[str] = Field(None, description="Player's last name")
    position: str = Field(..., description="Player position")
    team: Optional[str] = Field(None, description="NFL team abbreviation")
    status: Optional[PlayerStatus] = Field(None, description="Player status")
    injury_status: Optional[str] = Field(None, description="Injury status")
    height: Optional[str] = Field(None, description="Player height")
    weight: Optional[str] = Field(None, description="Player weight")
    age: Optional[int] = Field(None, ge=18, le=50, description="Player age")
    years_exp: Optional[int] = Field(None, ge=0, description="Years of experience")
    college: Optional[str] = Field(None, description="College attended")
    stats: Optional[Dict[str, Union[int, float]]] = Field(
        default_factory=dict, description="Player statistics"
    )
    fantasy_positions: Optional[List[str]] = Field(None, description="Fantasy eligible positions")
    
    @field_validator('position')
    @classmethod
    def validate_position(cls, v):
        """Validate position is a known NFL position."""
        if v is None:
            return v
        
        # Core fantasy positions
        fantasy_positions = {
            'QB', 'RB', 'WR', 'TE', 'K', 'DEF', 'HC'
        }
        
        # Defensive positions
        defensive_positions = {
            'DL', 'LB', 'DB', 'CB', 'SS', 'FS', 'DE', 'DT', 'NT', 'OLB', 'ILB', 'S'
        }
        
        # Offensive line positions
        oline_positions = {
            'OL', 'OT', 'OG', 'G', 'C', 'T'
        }
        
        # Special positions
        special_positions = {
            'P', 'LS', 'FB'
        }
        
        valid_positions = fantasy_positions | defensive_positions | oline_positions | special_positions
        
        if v not in valid_positions:
            # Log warning but don't fail validation for unknown positions
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Unknown position '{v}' - allowing but may need to update position list")
            
        return v


class TrendingPlayer(BaseModel):
    """Model for trending player data."""
    player_id: str = Field(..., description="Unique player identifier")
    count: int = Field(..., ge=0, description="Number of adds/drops")
    
    
class PlayerStats(BaseModel):
    """Model for player statistics."""
    player_id: str = Field(..., description="Unique player identifier")
    season: str = Field(..., pattern=r"^\d{4}$", description="Season year")
    season_type: str = Field(default="regular", description="Season type")
    week: Optional[int] = Field(None, ge=1, le=18, description="Week number")
    stats: Dict[str, Union[int, float]] = Field(..., description="Statistical data")
    
    @field_validator('stats')
    @classmethod
    def validate_stats(cls, v):
        """Validate that stats dictionary is not empty."""
        if not v:
            raise ValueError("Stats cannot be empty")
        return v


class Roster(BaseModel):
    """Model for team roster information."""
    roster_id: int = Field(..., ge=1, description="Unique roster identifier")
    owner_id: str = Field(..., description="User ID of roster owner")
    league_id: str = Field(..., description="League identifier")
    players: List[str] = Field(default_factory=list, description="List of player IDs")
    starters: List[str] = Field(default_factory=list, description="Starting lineup player IDs")
    reserve: Optional[List[str]] = Field(default_factory=list, description="Reserve player IDs")
    taxi: Optional[List[str]] = Field(default_factory=list, description="Taxi squad player IDs")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Roster settings")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional roster data")
    
    @model_validator(mode='after')
    def validate_starters_subset_of_players(self):
        """Validate that starters are reasonable (allow some flexibility for API inconsistencies)."""
        # Skip validation if either list is empty or None
        if not self.players or not self.starters:
            return self
            
        # Allow some flexibility - warn but don't fail if starters aren't all in players
        # This can happen when players are dropped mid-week but were starters
        players_set = set(self.players)
        starters_set = set(self.starters)
        if not starters_set.issubset(players_set):
            # Log warning but don't raise error to handle API inconsistencies
            import logging
            logger = logging.getLogger(__name__)
            missing_players = starters_set - players_set
            logger.warning(f"Roster {self.roster_id}: Some starters not in players list: {missing_players}")
        return self


class Matchup(BaseModel):
    """Model for matchup information."""
    matchup_id: Optional[int] = Field(None, description="Matchup identifier for the week")
    roster_id: int = Field(..., ge=1, description="Roster identifier")
    points: float = Field(default=0.0, ge=0, description="Points scored")
    points_bonus: Optional[float] = Field(default=0.0, description="Bonus points")
    players: List[str] = Field(default_factory=list, description="All rostered player IDs")
    starters: List[str] = Field(default_factory=list, description="Starting lineup player IDs")
    starters_points: Optional[List[float]] = Field(None, description="Points by starter position")
    players_points: Optional[Dict[str, float]] = Field(None, description="Points by player ID")
    custom_points: Optional[float] = Field(None, description="Custom scoring adjustments")
    
    @model_validator(mode='after')
    def validate_starters_in_players(self):
        """Validate that starters are subset of players."""
        if self.players and self.starters:
            players_set = set(self.players)
            starters_set = set(self.starters)
            if not starters_set.issubset(players_set):
                raise ValueError("All starters must be in the players list")
        return self


class MatchupScore(BaseModel):
    """Model for real-time matchup scoring."""
    matchup_id: int = Field(..., description="Matchup identifier")
    roster_id: int = Field(..., ge=1, description="Roster identifier")
    points: float = Field(..., ge=0, description="Current points scored")
    projected_points: Optional[float] = Field(None, description="Projected final points")
    players_points: Dict[str, float] = Field(..., description="Points by player ID")
    starters_points: List[float] = Field(..., description="Points by starter position")


class TradeProposal(BaseModel):
    """Model for trade proposal analysis."""
    target_roster_id: int = Field(..., description="Target roster for trade")
    give_players: List[str] = Field(..., description="Players to trade away")
    receive_players: List[str] = Field(..., description="Players to receive")
    trade_value: float = Field(..., description="Estimated trade value differential")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in trade analysis")


class TradeAnalysis(BaseModel):
    """Model for comprehensive trade analysis."""
    roster_id: int = Field(..., description="Analyzing roster ID")
    target_teams: List[int] = Field(..., description="Potential trade partner roster IDs")
    suggested_trades: List[TradeProposal] = Field(..., description="Recommended trade proposals")
    positional_needs: Dict[str, int] = Field(..., description="Positional strength ratings")
    trade_value_analysis: Dict[str, float] = Field(..., description="Player value assessments")


class RosterAnalysis(BaseModel):
    """Model for roster strength analysis."""
    roster_id: int = Field(..., description="Roster being analyzed")
    positional_strength: Dict[str, float] = Field(..., description="Strength by position (0-1)")
    weakest_positions: List[str] = Field(..., description="Positions needing improvement")
    strongest_positions: List[str] = Field(..., description="Positions of strength")
    overall_rating: float = Field(..., ge=0, le=1, description="Overall roster rating")
    recommendations: List[str] = Field(..., description="Improvement recommendations")


class ErrorResponse(BaseModel):
    """Model for error responses."""
    error_type: str = Field(..., description="Type of error encountered")
    message: str = Field(..., description="Human-readable error message")
    suggestions: Optional[List[str]] = Field(None, description="Suggested actions")
    retry_after: Optional[int] = Field(None, description="Seconds to wait before retry")