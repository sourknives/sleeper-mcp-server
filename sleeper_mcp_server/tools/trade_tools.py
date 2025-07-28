"""
Trade analysis tools for the Sleeper MCP server.

This module provides MCP tools for analyzing trade opportunities, evaluating
roster needs, and identifying potential trade partners in fantasy football leagues.
"""

import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from ..sleeper_client import SleeperClient, SleeperAPIError
from ..models import (
    League, Roster, Player, TradeAnalysis, TradeProposal, 
    RosterAnalysis, ErrorResponse
)
from ..cache import CacheManager, CacheDataType

logger = logging.getLogger(__name__)


class TradeTools:
    """Collection of MCP tools for trade analysis functionality."""
    
    def __init__(self, client: SleeperClient, cache: CacheManager):
        """
        Initialize trade tools.
        
        Args:
            client: Sleeper API client instance
            cache: Cache manager instance
        """
        self.client = client
        self.cache = cache
        
        # Standard fantasy football position groups and values
        self.position_groups = {
            'QB': ['QB'],
            'RB': ['RB'],
            'WR': ['WR'],
            'TE': ['TE'],
            'FLEX': ['RB', 'WR', 'TE'],
            'K': ['K'],
            'DEF': ['DEF']
        }
        
        # Position scarcity weights (higher = more scarce/valuable)
        self.position_scarcity = {
            'QB': 1.0,
            'RB': 1.5,
            'WR': 1.2,
            'TE': 1.8,
            'K': 0.5,
            'DEF': 0.7
        }
    
    async def analyze_trade_targets(
        self, 
        league_id: str, 
        roster_id: int, 
        position: Optional[str] = None
    ) -> dict:
        """
        Analyze potential trade targets for a roster based on positional needs.
        
        Args:
            league_id: League ID to analyze
            roster_id: Roster ID requesting trade analysis
            position: Optional position to focus analysis on
            
        Returns:
            Dictionary with trade analysis or error information
        """
        try:
            # Check cache first
            cache_key = f"trade_targets:{league_id}:{roster_id}:{position or 'all'}"
            cached_result = self.cache.get(cache_key, CacheDataType.ROSTER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get league information and rosters
            league = await self.client.get_league(league_id)
            if league is None:
                return {
                    "error": f"League '{league_id}' not found",
                    "suggestions": ["Verify the league ID is correct"]
                }
            
            rosters = await self.client.get_league_rosters(league_id)
            if not rosters:
                return {
                    "error": f"No rosters found for league '{league_id}'",
                    "suggestions": ["Check if the league has been set up with teams"]
                }
            
            # Find the requesting roster
            requesting_roster = None
            for roster in rosters:
                if roster.roster_id == roster_id:
                    requesting_roster = roster
                    break
            
            if requesting_roster is None:
                return {
                    "error": f"Roster ID {roster_id} not found in league",
                    "suggestions": ["Verify the roster ID is correct"]
                }
            
            # Get all players data
            all_players = await self.client.get_players("nfl")
            
            # Analyze roster needs
            roster_analysis = await self._analyze_roster_strength(
                requesting_roster, league, all_players
            )
            
            # Find potential trade partners
            trade_partners = await self._find_trade_partners(
                requesting_roster, rosters, league, all_players, position
            )
            
            # Generate trade proposals
            trade_proposals = await self._generate_trade_proposals(
                requesting_roster, trade_partners, league, all_players, position
            )
            
            # Calculate player values for context
            player_values = await self._calculate_player_values(
                requesting_roster.players, all_players
            )
            
            result = {
                "league_id": league_id,
                "roster_id": roster_id,
                "target_position": position,
                "roster_analysis": {
                    "positional_strength": roster_analysis["positional_strength"],
                    "weakest_positions": roster_analysis["weakest_positions"],
                    "strongest_positions": roster_analysis["strongest_positions"]
                },
                "target_teams": [partner["roster_id"] for partner in trade_partners],
                "suggested_trades": trade_proposals,
                "player_values": player_values,
                "analysis_summary": self._generate_analysis_summary(
                    roster_analysis, trade_partners, position
                )
            }
            
            # Cache the result for 15 minutes (trade landscape changes frequently)
            self.cache.set(cache_key, result, CacheDataType.ROSTER_DATA, ttl_override=900)
            
            logger.info(f"Generated trade analysis for roster {roster_id} in league {league_id}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error analyzing trade targets: {e}")
            return {
                "error": f"Failed to analyze trade targets: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error analyzing trade targets: {e}")
            return {
                "error": "An unexpected error occurred during trade analysis",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def evaluate_roster_needs(self, league_id: str, roster_id: int) -> dict:
        """
        Evaluate roster strengths and weaknesses across all positions.
        
        Args:
            league_id: League ID to analyze
            roster_id: Roster ID to evaluate
            
        Returns:
            Dictionary with roster analysis or error information
        """
        try:
            # Check cache first
            cache_key = f"roster_needs:{league_id}:{roster_id}"
            cached_result = self.cache.get(cache_key, CacheDataType.ROSTER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get league information and rosters
            league = await self.client.get_league(league_id)
            if league is None:
                return {
                    "error": f"League '{league_id}' not found",
                    "suggestions": ["Verify the league ID is correct"]
                }
            
            rosters = await self.client.get_league_rosters(league_id)
            if not rosters:
                return {
                    "error": f"No rosters found for league '{league_id}'",
                    "suggestions": ["Check if the league has been set up with teams"]
                }
            
            # Find the target roster
            target_roster = None
            for roster in rosters:
                if roster.roster_id == roster_id:
                    target_roster = roster
                    break
            
            if target_roster is None:
                return {
                    "error": f"Roster ID {roster_id} not found in league",
                    "suggestions": ["Verify the roster ID is correct"]
                }
            
            # Get all players data
            all_players = await self.client.get_players("nfl")
            
            # Perform detailed roster analysis
            analysis = await self._analyze_roster_strength(target_roster, league, all_players)
            
            # Add comparative analysis against league average
            league_comparison = await self._compare_to_league_average(
                target_roster, rosters, league, all_players
            )
            
            result = {
                "league_id": league_id,
                "roster_id": roster_id,
                "positional_strength": analysis["positional_strength"],
                "weakest_positions": analysis["weakest_positions"],
                "strongest_positions": analysis["strongest_positions"],
                "overall_rating": analysis["overall_rating"],
                "recommendations": analysis["recommendations"],
                "league_comparison": league_comparison,
                "depth_analysis": await self._analyze_roster_depth(
                    target_roster, league, all_players
                ),
                "starter_quality": await self._analyze_starter_quality(
                    target_roster, league, all_players
                )
            }
            
            # Cache the result for 15 minutes
            self.cache.set(cache_key, result, CacheDataType.ROSTER_DATA, ttl_override=900)
            
            logger.info(f"Evaluated roster needs for roster {roster_id} in league {league_id}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error evaluating roster needs: {e}")
            return {
                "error": f"Failed to evaluate roster needs: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error evaluating roster needs: {e}")
            return {
                "error": "An unexpected error occurred during roster evaluation",
                "suggestions": ["Try again in a few moments"]
            }   
 
    async def _analyze_roster_strength(
        self, 
        roster: Roster, 
        league: League, 
        all_players: Dict[str, Player]
    ) -> dict:
        """
        Analyze the strength of a roster across all positions.
        
        Args:
            roster: Roster to analyze
            league: League information
            all_players: Dictionary of all players
            
        Returns:
            Dictionary with positional strength analysis
        """
        # Get roster positions from league settings
        roster_positions = league.roster_positions
        
        # Categorize players by position
        position_players = defaultdict(list)
        for player_id in roster.players:
            if player_id in all_players:
                player = all_players[player_id]
                position_players[player.position].append(player)
        
        # Calculate positional strength (0.0 to 1.0 scale)
        positional_strength = {}
        position_needs = {}
        
        for position in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            # Count required starters for this position
            required_starters = roster_positions.count(position)
            flex_eligible = position in ['RB', 'WR', 'TE']
            if flex_eligible:
                required_starters += roster_positions.count('FLEX')
            
            players_at_position = position_players.get(position, [])
            player_count = len(players_at_position)
            
            if required_starters == 0:
                positional_strength[position] = 1.0  # Not needed
                position_needs[position] = 0
            else:
                # Base strength on player count vs requirements
                coverage_ratio = player_count / required_starters
                
                # Apply quality weighting (simplified - could be enhanced with stats)
                quality_bonus = min(0.2, player_count * 0.05)  # Bonus for depth
                
                strength = min(1.0, coverage_ratio * 0.8 + quality_bonus)
                positional_strength[position] = strength
                
                # Calculate need level (higher = more needed)
                if coverage_ratio < 1.0:
                    position_needs[position] = 3  # High need
                elif coverage_ratio < 1.5:
                    position_needs[position] = 2  # Medium need
                elif coverage_ratio < 2.0:
                    position_needs[position] = 1  # Low need
                else:
                    position_needs[position] = 0  # No need
        
        # Identify weakest and strongest positions
        sorted_positions = sorted(
            positional_strength.items(), 
            key=lambda x: x[1]
        )
        
        weakest_positions = [pos for pos, strength in sorted_positions[:3] if strength < 0.7]
        strongest_positions = [pos for pos, strength in sorted_positions[-3:] if strength > 0.8]
        
        # Calculate overall rating
        weighted_strength = sum(
            strength * self.position_scarcity.get(pos, 1.0)
            for pos, strength in positional_strength.items()
        )
        total_weight = sum(self.position_scarcity.get(pos, 1.0) for pos in positional_strength.keys())
        overall_rating = weighted_strength / total_weight if total_weight > 0 else 0.5
        
        # Generate recommendations
        recommendations = []
        for position in weakest_positions:
            if position_needs.get(position, 0) >= 2:
                recommendations.append(f"Consider acquiring {position} depth - currently weak position")
        
        if not recommendations:
            recommendations.append("Roster appears well-balanced across all positions")
        
        return {
            "positional_strength": positional_strength,
            "weakest_positions": weakest_positions,
            "strongest_positions": strongest_positions,
            "overall_rating": overall_rating,
            "recommendations": recommendations,
            "position_needs": position_needs
        }
    
    async def _find_trade_partners(
        self,
        requesting_roster: Roster,
        all_rosters: List[Roster],
        league: League,
        all_players: Dict[str, Player],
        target_position: Optional[str] = None
    ) -> List[dict]:
        """
        Find potential trade partners based on complementary needs.
        
        Args:
            requesting_roster: The roster looking for trades
            all_rosters: All rosters in the league
            league: League information
            all_players: Dictionary of all players
            target_position: Optional position to focus on
            
        Returns:
            List of potential trade partners with analysis
        """
        requesting_analysis = await self._analyze_roster_strength(
            requesting_roster, league, all_players
        )
        
        trade_partners = []
        
        for roster in all_rosters:
            if roster.roster_id == requesting_roster.roster_id:
                continue  # Skip self
            
            partner_analysis = await self._analyze_roster_strength(
                roster, league, all_players
            )
            
            # Calculate complementary score
            complementary_score = self._calculate_complementary_score(
                requesting_analysis, partner_analysis, target_position
            )
            
            if complementary_score > 0.3:  # Threshold for viable trade partner
                trade_partners.append({
                    "roster_id": roster.roster_id,
                    "owner_id": roster.owner_id,
                    "complementary_score": complementary_score,
                    "their_strengths": partner_analysis["strongest_positions"],
                    "their_weaknesses": partner_analysis["weakest_positions"],
                    "mutual_benefit_positions": self._find_mutual_benefit_positions(
                        requesting_analysis, partner_analysis
                    )
                })
        
        # Sort by complementary score (highest first)
        trade_partners.sort(key=lambda x: x["complementary_score"], reverse=True)
        
        return trade_partners[:5]  # Return top 5 partners
    
    def _calculate_complementary_score(
        self,
        requesting_analysis: dict,
        partner_analysis: dict,
        target_position: Optional[str] = None
    ) -> float:
        """
        Calculate how complementary two rosters are for trading.
        
        Args:
            requesting_analysis: Analysis of requesting roster
            partner_analysis: Analysis of potential partner roster
            target_position: Optional position to focus scoring on
            
        Returns:
            Complementary score (0.0 to 1.0)
        """
        score = 0.0
        
        req_strengths = set(requesting_analysis["strongest_positions"])
        req_weaknesses = set(requesting_analysis["weakest_positions"])
        partner_strengths = set(partner_analysis["strongest_positions"])
        partner_weaknesses = set(partner_analysis["weakest_positions"])
        
        # Score based on complementary strengths/weaknesses
        mutual_help = len(req_weaknesses & partner_strengths) + len(req_strengths & partner_weaknesses)
        max_mutual_help = len(req_weaknesses) + len(req_strengths)
        
        if max_mutual_help > 0:
            score += (mutual_help / max_mutual_help) * 0.6
        
        # Bonus if target position is involved
        if target_position:
            if target_position in partner_strengths and target_position in req_weaknesses:
                score += 0.3
            elif target_position in req_strengths and target_position in partner_weaknesses:
                score += 0.2
        
        # Penalty for similar roster construction (less trading opportunity)
        similarity_penalty = len(req_strengths & partner_strengths) * 0.1
        score = max(0.0, score - similarity_penalty)
        
        return min(1.0, score)
    
    def _find_mutual_benefit_positions(
        self, 
        requesting_analysis: dict, 
        partner_analysis: dict
    ) -> List[str]:
        """
        Find positions where both teams could benefit from trading.
        
        Args:
            requesting_analysis: Analysis of requesting roster
            partner_analysis: Analysis of partner roster
            
        Returns:
            List of positions with mutual benefit potential
        """
        req_strengths = set(requesting_analysis["strongest_positions"])
        req_weaknesses = set(requesting_analysis["weakest_positions"])
        partner_strengths = set(partner_analysis["strongest_positions"])
        partner_weaknesses = set(partner_analysis["weakest_positions"])
        
        mutual_positions = []
        
        # Positions where requester is strong and partner is weak
        for position in req_strengths & partner_weaknesses:
            mutual_positions.append(position)
        
        # Positions where partner is strong and requester is weak
        for position in partner_strengths & req_weaknesses:
            mutual_positions.append(position)
        
        return list(set(mutual_positions))  # Remove duplicates
    
    async def _generate_trade_proposals(
        self,
        requesting_roster: Roster,
        trade_partners: List[dict],
        league: League,
        all_players: Dict[str, Player],
        target_position: Optional[str] = None
    ) -> List[dict]:
        """
        Generate specific trade proposals with trade partners.
        
        Args:
            requesting_roster: The roster looking for trades
            trade_partners: List of potential trade partners
            league: League information
            all_players: Dictionary of all players
            target_position: Optional position to focus on
            
        Returns:
            List of trade proposals
        """
        proposals = []
        
        # Get requesting roster's players by position
        req_players_by_pos = defaultdict(list)
        for player_id in requesting_roster.players:
            if player_id in all_players:
                player = all_players[player_id]
                req_players_by_pos[player.position].append(player)
        
        for partner in trade_partners[:3]:  # Top 3 partners
            partner_roster = None
            # Find the partner roster object (simplified - in real implementation, pass this in)
            # For now, create a basic proposal structure
            
            mutual_positions = partner["mutual_benefit_positions"]
            
            for position in mutual_positions:
                if target_position and position != target_position:
                    continue
                
                # Create a basic trade proposal
                proposal = {
                    "target_roster_id": partner["roster_id"],
                    "target_position": position,
                    "trade_rationale": f"Address {position} needs through complementary roster strengths",
                    "confidence": partner["complementary_score"],
                    "estimated_benefit": "Mutual positional improvement"
                }
                
                proposals.append(proposal)
        
        return proposals[:5]  # Return top 5 proposals
    
    async def _calculate_player_values(
        self, 
        player_ids: List[str], 
        all_players: Dict[str, Player]
    ) -> Dict[str, float]:
        """
        Calculate relative values for players (simplified implementation).
        
        Args:
            player_ids: List of player IDs to value
            all_players: Dictionary of all players
            
        Returns:
            Dictionary mapping player IDs to relative values
        """
        values = {}
        
        for player_id in player_ids:
            if player_id in all_players:
                player = all_players[player_id]
                
                # Simplified valuation based on position scarcity
                base_value = self.position_scarcity.get(player.position, 1.0)
                
                # Adjust for player status
                if player.status and player.status.value == "Active":
                    status_multiplier = 1.0
                else:
                    status_multiplier = 0.5
                
                values[player_id] = base_value * status_multiplier
        
        return values
    
    def _generate_analysis_summary(
        self,
        roster_analysis: dict,
        trade_partners: List[dict],
        target_position: Optional[str] = None
    ) -> str:
        """
        Generate a human-readable summary of the trade analysis.
        
        Args:
            roster_analysis: Analysis of the requesting roster
            trade_partners: List of potential trade partners
            target_position: Optional target position
            
        Returns:
            Summary string
        """
        summary_parts = []
        
        # Roster strength summary
        overall_rating = roster_analysis["overall_rating"]
        if overall_rating > 0.8:
            summary_parts.append("Your roster is very strong overall.")
        elif overall_rating > 0.6:
            summary_parts.append("Your roster has good balance with some areas for improvement.")
        else:
            summary_parts.append("Your roster has significant weaknesses that could be addressed through trades.")
        
        # Weakness summary
        weaknesses = roster_analysis["weakest_positions"]
        if weaknesses:
            summary_parts.append(f"Weakest positions: {', '.join(weaknesses)}")
        
        # Trade partner summary
        if trade_partners:
            summary_parts.append(f"Found {len(trade_partners)} potential trade partners.")
            if target_position:
                summary_parts.append(f"Focus on acquiring {target_position} talent.")
        else:
            summary_parts.append("Limited trade opportunities identified in current league.")
        
        return " ".join(summary_parts)
    
    async def _compare_to_league_average(
        self,
        target_roster: Roster,
        all_rosters: List[Roster],
        league: League,
        all_players: Dict[str, Player]
    ) -> Dict[str, float]:
        """
        Compare roster strength to league average.
        
        Args:
            target_roster: Roster to compare
            all_rosters: All rosters in league
            league: League information
            all_players: Dictionary of all players
            
        Returns:
            Dictionary with comparison metrics
        """
        # Calculate league averages
        league_strengths = defaultdict(list)
        
        for roster in all_rosters:
            analysis = await self._analyze_roster_strength(roster, league, all_players)
            for position, strength in analysis["positional_strength"].items():
                league_strengths[position].append(strength)
        
        # Calculate averages
        league_averages = {}
        for position, strengths in league_strengths.items():
            league_averages[position] = sum(strengths) / len(strengths) if strengths else 0.5
        
        # Compare target roster to averages
        target_analysis = await self._analyze_roster_strength(target_roster, league, all_players)
        comparison = {}
        
        for position, target_strength in target_analysis["positional_strength"].items():
            league_avg = league_averages.get(position, 0.5)
            comparison[position] = target_strength - league_avg  # Positive = above average
        
        return comparison
    
    async def _analyze_roster_depth(
        self,
        roster: Roster,
        league: League,
        all_players: Dict[str, Player]
    ) -> Dict[str, int]:
        """
        Analyze roster depth at each position.
        
        Args:
            roster: Roster to analyze
            league: League information
            all_players: Dictionary of all players
            
        Returns:
            Dictionary with depth counts by position
        """
        depth_analysis = {}
        
        # Count players by position
        for position in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            count = 0
            for player_id in roster.players:
                if player_id in all_players:
                    player = all_players[player_id]
                    if player.position == position:
                        count += 1
            depth_analysis[position] = count
        
        return depth_analysis
    
    async def _analyze_starter_quality(
        self,
        roster: Roster,
        league: League,
        all_players: Dict[str, Player]
    ) -> Dict[str, str]:
        """
        Analyze the quality of likely starters.
        
        Args:
            roster: Roster to analyze
            league: League information
            all_players: Dictionary of all players
            
        Returns:
            Dictionary with starter quality assessment
        """
        starter_quality = {}
        
        # Simplified starter quality assessment
        for position in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            position_players = []
            for player_id in roster.players:
                if player_id in all_players:
                    player = all_players[player_id]
                    if player.position == position:
                        position_players.append(player)
            
            if position_players:
                # Simplified quality assessment based on active status
                active_count = sum(1 for p in position_players if p.status and p.status.value == "Active")
                total_count = len(position_players)
                
                if active_count == 0:
                    starter_quality[position] = "Poor - No active players"
                elif active_count / total_count > 0.8:
                    starter_quality[position] = "Good - Mostly active players"
                else:
                    starter_quality[position] = "Average - Mixed active/inactive"
            else:
                starter_quality[position] = "None - No players at position"
        
        return starter_quality