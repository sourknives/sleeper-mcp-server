"""
Commissioner tools for the Sleeper MCP server.

This module provides MCP tools for league commissioners to evaluate trade fairness
and detect potential collusion patterns in fantasy football leagues.
"""

import logging
from typing import Dict, List, Optional

from ..sleeper_client import SleeperClient, SleeperAPIError
from ..models import (
    League, Roster, Player, User, CommissionerTradeEvaluation, 
    CollusionAnalysis, ErrorResponse
)
from ..cache import CacheManager, CacheDataType
from ..utils.commissioner_evaluator import CommissionerEvaluator

logger = logging.getLogger(__name__)


class CommissionerTools:
    """Collection of MCP tools for commissioner functionality."""
    
    def __init__(self, client: SleeperClient, cache: CacheManager):
        """
        Initialize commissioner tools.
        
        Args:
            client: Sleeper API client instance
            cache: Cache manager instance
        """
        self.client = client
        self.cache = cache
        self.evaluator = CommissionerEvaluator()
    
    async def evaluate_trade_fairness(
        self,
        league_id: str,
        team_a_roster_id: int,
        team_a_gives: List[str],
        team_b_roster_id: int,
        team_b_gives: List[str],
        scoring_format: str = "half_ppr",
        current_week: int = 1,
        playoff_start_week: int = 14
    ) -> dict:
        """
        Evaluate trade fairness with comprehensive commissioner analysis.
        
        Args:
            league_id: League ID where the trade is happening
            team_a_roster_id: First team's roster ID
            team_a_gives: List of player IDs team A is trading away
            team_b_roster_id: Second team's roster ID
            team_b_gives: List of player IDs team B is trading away
            scoring_format: Scoring format ("ppr" or "half_ppr")
            current_week: Current week number
            playoff_start_week: Week when playoffs start
            
        Returns:
            Dictionary with comprehensive trade fairness evaluation or error information
        """
        try:
            # Validate inputs
            if not self._validate_commissioner_inputs(
                league_id, team_a_roster_id, team_a_gives, team_b_roster_id, team_b_gives, scoring_format
            ):
                return {
                    "error": "Invalid input parameters",
                    "suggestions": [
                        "Ensure all required parameters are provided",
                        "Verify roster IDs are integers",
                        "Check that player lists are not empty",
                        "Use 'ppr' or 'half_ppr' for scoring format"
                    ]
                }
            
            # Check cache first
            cache_key = f"trade_fairness:{league_id}:{team_a_roster_id}:{team_b_roster_id}:{hash(tuple(sorted(team_a_gives + team_b_gives)))}:{scoring_format}:{current_week}"
            cached_result = self.cache.get(cache_key, CacheDataType.ROSTER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get league information
            league = await self.client.get_league(league_id)
            if league is None:
                return {
                    "error": f"League '{league_id}' not found",
                    "suggestions": ["Verify the league ID is correct"]
                }
            
            # Get all rosters
            rosters = await self.client.get_league_rosters(league_id)
            if not rosters:
                return {
                    "error": f"No rosters found for league '{league_id}'",
                    "suggestions": ["Check if the league has been set up with teams"]
                }
            
            # Find the two rosters involved in the trade
            team_a_roster = None
            team_b_roster = None
            for roster in rosters:
                if roster.roster_id == team_a_roster_id:
                    team_a_roster = roster
                elif roster.roster_id == team_b_roster_id:
                    team_b_roster = roster
            
            if team_a_roster is None:
                return {
                    "error": f"Team A roster ID {team_a_roster_id} not found in league",
                    "suggestions": ["Verify the roster ID is correct"]
                }
            
            if team_b_roster is None:
                return {
                    "error": f"Team B roster ID {team_b_roster_id} not found in league",
                    "suggestions": ["Verify the roster ID is correct"]
                }
            
            # Validate that players belong to the correct teams
            validation_error = self._validate_player_ownership(
                team_a_roster, team_a_gives, team_b_roster, team_b_gives
            )
            if validation_error:
                return validation_error
            
            # Get all players data
            all_players = await self.client.get_players("nfl")
            
            # Get league users
            league_users = await self.client.get_league_users(league_id)
            users_dict = {user.user_id: user for user in league_users} if league_users else {}
            
            # Perform comprehensive fairness evaluation
            evaluation = await self.evaluator.evaluate_trade_fairness(
                team_a_roster=team_a_roster,
                team_a_gives=team_a_gives,
                team_b_roster=team_b_roster,
                team_b_gives=team_b_gives,
                league=league,
                all_players=all_players,
                league_users=users_dict,
                scoring_format=scoring_format,
                current_week=current_week,
                playoff_start_week=playoff_start_week
            )
            
            # Format result for MCP response
            result = {
                "league_id": league_id,
                "team_a_roster_id": team_a_roster_id,
                "team_b_roster_id": team_b_roster_id,
                "team_a_gives": team_a_gives,
                "team_b_gives": team_b_gives,
                "scoring_format": scoring_format,
                "current_week": current_week,
                "playoff_start_week": playoff_start_week,
                "fairness_score": evaluation["fairness_score"],
                "value_analysis": evaluation["value_analysis"],
                "positional_analysis": evaluation["positional_analysis"],
                "roster_impact": evaluation["roster_impact"],
                "performance_analysis": evaluation["performance_analysis"],
                "injury_analysis": evaluation["injury_analysis"],
                "league_context": evaluation["league_context"],
                "recommendation": evaluation["recommendation"],
                "concerns": evaluation["concerns"],
                "confidence_level": evaluation["confidence_level"],
                "evaluation_timestamp": evaluation["evaluation_timestamp"],
                "commissioner_notes": self._generate_commissioner_notes(evaluation)
            }
            
            # Cache the result for 30 minutes
            self.cache.set(cache_key, result, CacheDataType.ROSTER_DATA, ttl_override=1800)
            
            logger.info(f"Evaluated trade fairness between rosters {team_a_roster_id} and {team_b_roster_id} in league {league_id}")
            return result
            
        except ValueError as e:
            logger.error(f"Validation error in trade fairness evaluation: {e}")
            return {
                "error": str(e),
                "suggestions": ["Check that all player IDs are valid and belong to the correct teams"]
            }
        except SleeperAPIError as e:
            logger.error(f"API error evaluating trade fairness: {e}")
            return {
                "error": f"Failed to evaluate trade fairness: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error evaluating trade fairness: {e}")
            return {
                "error": "An unexpected error occurred during trade fairness evaluation",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def detect_trade_collusion(
        self,
        league_id: str,
        team_a_roster_id: int,
        team_b_roster_id: int,
        team_a_gives: List[str],
        team_b_gives: List[str],
        trade_history_weeks: Optional[int] = 8,
        current_week: int = 1,
        playoff_start_week: int = 14
    ) -> dict:
        """
        Detect potential collusion patterns in trade proposals.
        
        Args:
            league_id: League ID where the trade is happening
            team_a_roster_id: First team's roster ID
            team_b_roster_id: Second team's roster ID
            team_a_gives: List of player IDs team A is trading away
            team_b_gives: List of player IDs team B is trading away
            trade_history_weeks: Number of weeks of trade history to analyze
            current_week: Current week number
            playoff_start_week: Week when playoffs start
            
        Returns:
            Dictionary with collusion analysis results or error information
        """
        try:
            # Validate inputs
            if not self._validate_commissioner_inputs(
                league_id, team_a_roster_id, team_a_gives, team_b_roster_id, team_b_gives
            ):
                return {
                    "error": "Invalid input parameters",
                    "suggestions": [
                        "Ensure all required parameters are provided",
                        "Verify roster IDs are integers",
                        "Check that player lists are not empty"
                    ]
                }
            
            # Check cache first
            cache_key = f"trade_collusion:{league_id}:{team_a_roster_id}:{team_b_roster_id}:{hash(tuple(sorted(team_a_gives + team_b_gives)))}:{trade_history_weeks}:{current_week}"
            cached_result = self.cache.get(cache_key, CacheDataType.ROSTER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get league information
            league = await self.client.get_league(league_id)
            if league is None:
                return {
                    "error": f"League '{league_id}' not found",
                    "suggestions": ["Verify the league ID is correct"]
                }
            
            # Get all rosters
            rosters = await self.client.get_league_rosters(league_id)
            if not rosters:
                return {
                    "error": f"No rosters found for league '{league_id}'",
                    "suggestions": ["Check if the league has been set up with teams"]
                }
            
            # Find the two rosters involved in the trade
            team_a_roster = None
            team_b_roster = None
            for roster in rosters:
                if roster.roster_id == team_a_roster_id:
                    team_a_roster = roster
                elif roster.roster_id == team_b_roster_id:
                    team_b_roster = roster
            
            if team_a_roster is None:
                return {
                    "error": f"Team A roster ID {team_a_roster_id} not found in league",
                    "suggestions": ["Verify the roster ID is correct"]
                }
            
            if team_b_roster is None:
                return {
                    "error": f"Team B roster ID {team_b_roster_id} not found in league",
                    "suggestions": ["Verify the roster ID is correct"]
                }
            
            # Validate that players belong to the correct teams
            validation_error = self._validate_player_ownership(
                team_a_roster, team_a_gives, team_b_roster, team_b_gives
            )
            if validation_error:
                return validation_error
            
            # Get all players data
            all_players = await self.client.get_players("nfl")
            
            # Get league users
            league_users = await self.client.get_league_users(league_id)
            users_dict = {user.user_id: user for user in league_users} if league_users else {}
            
            # Get trade history (simplified - in a real implementation, this would come from Sleeper API)
            # For now, we'll pass None and let the evaluator work without historical data
            trade_history = None
            
            # Perform collusion detection analysis
            analysis = await self.evaluator.detect_trade_collusion(
                team_a_roster=team_a_roster,
                team_b_roster=team_b_roster,
                team_a_gives=team_a_gives,
                team_b_gives=team_b_gives,
                league=league,
                all_players=all_players,
                league_users=users_dict,
                trade_history=trade_history,
                current_week=current_week,
                playoff_start_week=playoff_start_week
            )
            
            # Format result for MCP response
            result = {
                "league_id": league_id,
                "team_a_roster_id": team_a_roster_id,
                "team_b_roster_id": team_b_roster_id,
                "team_a_gives": team_a_gives,
                "team_b_gives": team_b_gives,
                "trade_history_weeks": trade_history_weeks,
                "current_week": current_week,
                "playoff_start_week": playoff_start_week,
                "collusion_risk": analysis["collusion_risk"],
                "risk_factors": analysis["risk_factors"],
                "value_imbalance_percentage": analysis["value_imbalance_percentage"],
                "recommendation": analysis["recommendation"],
                "investigation_priority": analysis["investigation_priority"],
                "suggested_actions": analysis["suggested_actions"],
                "analysis_timestamp": analysis["analysis_timestamp"],
                "commissioner_summary": self._generate_collusion_summary(analysis)
            }
            
            # Cache the result for 30 minutes
            self.cache.set(cache_key, result, CacheDataType.ROSTER_DATA, ttl_override=1800)
            
            logger.info(f"Analyzed trade collusion between rosters {team_a_roster_id} and {team_b_roster_id} in league {league_id}")
            return result
            
        except ValueError as e:
            logger.error(f"Validation error in collusion detection: {e}")
            return {
                "error": str(e),
                "suggestions": ["Check that all player IDs are valid and belong to the correct teams"]
            }
        except SleeperAPIError as e:
            logger.error(f"API error detecting trade collusion: {e}")
            return {
                "error": f"Failed to detect trade collusion: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error detecting trade collusion: {e}")
            return {
                "error": "An unexpected error occurred during collusion detection",
                "suggestions": ["Try again in a few moments"]
            }
    
    def _validate_commissioner_inputs(
        self,
        league_id: str,
        team_a_roster_id: int,
        team_a_gives: List[str],
        team_b_roster_id: int,
        team_b_gives: List[str],
        scoring_format: str = "half_ppr"
    ) -> bool:
        """
        Validate commissioner tool inputs.
        
        Args:
            league_id: League ID
            team_a_roster_id: Team A roster ID
            team_a_gives: Players team A gives
            team_b_roster_id: Team B roster ID
            team_b_gives: Players team B gives
            scoring_format: Scoring format
            
        Returns:
            True if inputs are valid, False otherwise
        """
        # Check required parameters
        if not league_id or not isinstance(league_id, str):
            return False
        
        if not isinstance(team_a_roster_id, int) or team_a_roster_id <= 0:
            return False
        
        if not isinstance(team_b_roster_id, int) or team_b_roster_id <= 0:
            return False
        
        if team_a_roster_id == team_b_roster_id:
            return False
        
        if not team_a_gives or not isinstance(team_a_gives, list):
            return False
        
        if not team_b_gives or not isinstance(team_b_gives, list):
            return False
        
        # Check that all player IDs are strings
        if not all(isinstance(pid, str) and pid.strip() for pid in team_a_gives):
            return False
        
        if not all(isinstance(pid, str) and pid.strip() for pid in team_b_gives):
            return False
        
        # Check scoring format if provided
        if scoring_format and scoring_format not in ["ppr", "half_ppr"]:
            return False
        
        return True
    
    def _validate_player_ownership(
        self,
        team_a_roster: Roster,
        team_a_gives: List[str],
        team_b_roster: Roster,
        team_b_gives: List[str]
    ) -> Optional[dict]:
        """
        Validate that players belong to the correct teams.
        
        Args:
            team_a_roster: Team A roster
            team_a_gives: Players team A is giving
            team_b_roster: Team B roster
            team_b_gives: Players team B is giving
            
        Returns:
            Error dictionary if validation fails, None if valid
        """
        team_a_player_set = set(team_a_roster.players)
        team_b_player_set = set(team_b_roster.players)
        
        for player_id in team_a_gives:
            if player_id not in team_a_player_set:
                return {
                    "error": f"Player {player_id} is not on team A's roster",
                    "suggestions": ["Verify all player IDs belong to the correct teams"]
                }
        
        for player_id in team_b_gives:
            if player_id not in team_b_player_set:
                return {
                    "error": f"Player {player_id} is not on team B's roster",
                    "suggestions": ["Verify all player IDs belong to the correct teams"]
                }
        
        return None
    
    def _generate_commissioner_notes(self, evaluation: Dict) -> List[str]:
        """
        Generate helpful commissioner notes based on evaluation results.
        
        Args:
            evaluation: Trade fairness evaluation results
            
        Returns:
            List of commissioner notes
        """
        notes = []
        
        fairness_score = evaluation.get("fairness_score", 0)
        recommendation = evaluation.get("recommendation", "")
        concerns = evaluation.get("concerns", [])
        
        # Add score interpretation
        if fairness_score >= 85:
            notes.append("Trade shows excellent fairness - minimal commissioner oversight needed")
        elif fairness_score >= 70:
            notes.append("Trade appears fair with good balance between teams")
        elif fairness_score >= 55:
            notes.append("Trade is within acceptable fairness range but monitor for concerns")
        elif fairness_score >= 40:
            notes.append("Trade raises fairness questions - consider additional review")
        else:
            notes.append("Trade shows significant fairness issues - strong consideration for veto")
        
        # Add specific guidance based on recommendation
        if recommendation == "APPROVE":
            notes.append("Trade meets league fairness standards and can be approved")
        elif recommendation == "INVESTIGATE":
            notes.append("Consider reaching out to both teams for trade rationale")
            notes.append("Review team needs and roster construction for context")
        elif recommendation == "VETO":
            notes.append("Trade appears to significantly harm league competitive balance")
            notes.append("Consider discussing with league members before final decision")
        
        # Add concern-specific notes
        if concerns:
            notes.append("Key areas of concern identified:")
            for concern in concerns[:3]:  # Limit to top 3 concerns
                notes.append(f"  • {concern}")
        
        return notes
    
    def _generate_collusion_summary(self, analysis: Dict) -> Dict[str, str]:
        """
        Generate a summary of collusion analysis for commissioners.
        
        Args:
            analysis: Collusion analysis results
            
        Returns:
            Dictionary with collusion summary information
        """
        risk_level = analysis.get("collusion_risk", "LOW")
        risk_factors = analysis.get("risk_factors", [])
        recommendation = analysis.get("recommendation", "")
        
        summary = {
            "risk_assessment": "",
            "primary_concerns": "",
            "recommended_action": "",
            "investigation_notes": ""
        }
        
        # Risk assessment summary
        if risk_level == "LOW":
            summary["risk_assessment"] = "Trade shows minimal collusion indicators and appears legitimate"
        elif risk_level == "MEDIUM":
            summary["risk_assessment"] = "Trade has some concerning patterns that warrant closer examination"
        else:  # HIGH
            summary["risk_assessment"] = "Trade exhibits multiple suspicious patterns suggesting possible collusion"
        
        # Primary concerns
        if risk_factors:
            high_severity_factors = [rf for rf in risk_factors if rf.get("severity") == "HIGH"]
            if high_severity_factors:
                primary_factor = high_severity_factors[0]
                summary["primary_concerns"] = primary_factor.get("description", "Multiple high-severity concerns identified")
            else:
                summary["primary_concerns"] = f"{len(risk_factors)} risk factors identified requiring review"
        else:
            summary["primary_concerns"] = "No significant collusion indicators detected"
        
        # Recommended action
        if recommendation:
            summary["recommended_action"] = recommendation
        else:
            summary["recommended_action"] = "Monitor trade but no immediate action required"
        
        # Investigation notes
        if risk_level in ["MEDIUM", "HIGH"]:
            summary["investigation_notes"] = "Consider reviewing trading history between these teams and their motivations for this specific trade"
        else:
            summary["investigation_notes"] = "No additional investigation recommended at this time"
        
        return summary