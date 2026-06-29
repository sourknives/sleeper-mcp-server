"""
Advanced trade package evaluation system for fantasy football.

This module provides comprehensive analysis of trade packages including fair value
calculations, roster fit analysis, acceptance probability modeling, and trade
recommendations with supporting rationale.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import math

from ..models import (
    Player, Roster, League, TradePackageAnalysis, FairValueAnalysis,
    RosterFitAnalysis, PlayerRanking
)

logger = logging.getLogger(__name__)


class TradeAnalyzer:
    """
    Advanced trade package evaluation system that provides comprehensive analysis
    similar to FantasyPros Trade Analyzer functionality.
    """
    
    def __init__(self):
        """Initialize the trade analyzer with position values and scoring weights."""
        
        # Position scarcity multipliers (higher = more scarce/valuable)
        self.position_scarcity = {
            'QB': 1.0,
            'RB': 1.4,  # RB scarcity premium
            'WR': 1.1,
            'TE': 1.6,  # TE scarcity premium
            'K': 0.6,
            'DEF': 0.7
        }
        
        # Position importance weights for roster construction
        self.position_importance = {
            'QB': 0.20,
            'RB': 0.25,
            'WR': 0.25,
            'TE': 0.15,
            'K': 0.05,
            'DEF': 0.10
        }
        
        # Starter vs bench value multipliers
        self.starter_multiplier = 1.0
        self.bench_multiplier = 0.4
        
        # Trade acceptance probability factors
        self.acceptance_factors = {
            'fair_value_weight': 0.35,
            'roster_fit_weight': 0.40,
            'positional_need_weight': 0.25
        }
    
    async def evaluate_trade_package(
        self,
        team_a_roster: Roster,
        team_a_gives: List[str],
        team_b_roster: Roster,
        team_b_gives: List[str],
        league: League,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None,
        scoring_format: str = "half_ppr"
    ) -> TradePackageAnalysis:
        """
        Evaluate a complete trade package between two teams.
        
        Args:
            team_a_roster: First team's roster
            team_a_gives: List of player IDs team A is trading away
            team_b_roster: Second team's roster
            team_b_gives: List of player IDs team B is trading away
            league: League information
            all_players: Dictionary of all players
            player_rankings: Optional player rankings data
            scoring_format: Scoring format ("ppr" or "half_ppr")
            
        Returns:
            TradePackageAnalysis with comprehensive evaluation
        """
        try:
            # Validate trade package
            self._validate_trade_package(team_a_gives, team_b_gives, all_players)
            
            # Calculate fair value analysis
            fair_value = await self._calculate_fair_value(
                team_a_gives, team_b_gives, all_players, player_rankings, scoring_format
            )
            
            # Calculate positional adjustments
            positional_adjustments = self._calculate_positional_adjustments(
                team_a_gives, team_b_gives, all_players
            )
            
            # Analyze roster fit improvement
            roster_fit = await self._analyze_roster_fit_improvement(
                team_a_roster, team_a_gives, team_b_gives,
                team_b_roster, team_b_gives, team_a_gives,
                league, all_players, player_rankings
            )
            
            # Calculate acceptance probability
            acceptance_prob = self._calculate_acceptance_probability(
                fair_value, roster_fit, positional_adjustments
            )
            
            # Generate recommendation and rationale
            recommendation, rationale = self._generate_recommendation_and_rationale(
                fair_value, roster_fit, acceptance_prob, positional_adjustments,
                team_a_gives, team_b_gives, all_players
            )
            
            return TradePackageAnalysis(
                fair_value_analysis=fair_value,
                positional_adjustments=positional_adjustments,
                roster_fit_improvement=roster_fit,
                acceptance_probability=acceptance_prob,
                recommendation=recommendation,
                rationale=rationale
            )
            
        except Exception as e:
            logger.error(f"Error evaluating trade package: {e}")
            raise
    
    def _validate_trade_package(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> None:
        """
        Validate that the trade package is valid.
        
        Args:
            team_a_gives: Players team A is trading away
            team_b_gives: Players team B is trading away
            all_players: Dictionary of all players
            
        Raises:
            ValueError: If trade package is invalid
        """
        if not team_a_gives or not team_b_gives:
            raise ValueError("Both teams must trade at least one player")
        
        # Validate all players exist
        for player_id in team_a_gives + team_b_gives:
            if player_id not in all_players:
                raise ValueError(f"Player ID {player_id} not found")
        
        # Check for duplicate players
        all_traded_players = team_a_gives + team_b_gives
        if len(all_traded_players) != len(set(all_traded_players)):
            raise ValueError("Cannot trade the same player multiple times")
    
    async def _calculate_fair_value(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None,
        scoring_format: str = "half_ppr"
    ) -> FairValueAnalysis:
        """
        Calculate fair value analysis using projected points.
        
        Args:
            team_a_gives: Players team A is trading away
            team_b_gives: Players team B is trading away
            all_players: Dictionary of all players
            player_rankings: Optional player rankings data
            scoring_format: Scoring format for projections
            
        Returns:
            FairValueAnalysis with point totals and differentials
        """
        team_a_points = 0.0
        team_b_points = 0.0
        
        # Calculate team A's traded player values
        for player_id in team_a_gives:
            points = self._get_player_projected_points(
                player_id, all_players, player_rankings, scoring_format
            )
            team_a_points += points
        
        # Calculate team B's traded player values
        for player_id in team_b_gives:
            points = self._get_player_projected_points(
                player_id, all_players, player_rankings, scoring_format
            )
            team_b_points += points
        
        # Calculate differential and ratio
        point_differential = team_a_points - team_b_points
        value_ratio = team_a_points / team_b_points if team_b_points > 0 else float('inf')
        
        return FairValueAnalysis(
            team_a_total_points=team_a_points,
            team_b_total_points=team_b_points,
            point_differential=point_differential,
            value_ratio=value_ratio
        )
    
    def _get_player_projected_points(
        self,
        player_id: str,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None,
        scoring_format: str = "half_ppr"
    ) -> float:
        """
        Get projected points for a player.
        
        Args:
            player_id: Player ID
            all_players: Dictionary of all players
            player_rankings: Optional player rankings data
            scoring_format: Scoring format
            
        Returns:
            Projected points for the player
        """
        if player_rankings and player_id in player_rankings:
            return player_rankings[player_id].projected_points
        
        # Fallback to position-based estimates if no rankings available
        if player_id not in all_players:
            return 0.0
        
        player = all_players[player_id]
        position = player.position
        
        # Default projected points by position (rest of season estimates)
        position_defaults = {
            'QB': 180.0,
            'RB': 120.0,
            'WR': 110.0,
            'TE': 90.0,
            'K': 80.0,
            'DEF': 85.0
        }
        
        base_points = position_defaults.get(position, 50.0)
        
        # Adjust for player status
        if player.status and player.status.value != "Active":
            base_points *= 0.3  # Significant reduction for inactive players
        
        return base_points
    
    def _calculate_positional_adjustments(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> Dict[str, float]:
        """
        Calculate positional scarcity adjustments.
        
        Args:
            team_a_gives: Players team A is trading away
            team_b_gives: Players team B is trading away
            all_players: Dictionary of all players
            
        Returns:
            Dictionary with positional adjustment values
        """
        adjustments = {}
        
        # Calculate adjustments for team A (what they're giving up)
        team_a_adjustment = 0.0
        for player_id in team_a_gives:
            if player_id in all_players:
                player = all_players[player_id]
                scarcity_multiplier = self.position_scarcity.get(player.position, 1.0)
                base_points = self._get_player_projected_points(player_id, all_players)
                adjustment = base_points * (scarcity_multiplier - 1.0)
                team_a_adjustment += adjustment
        
        # Calculate adjustments for team B (what they're giving up)
        team_b_adjustment = 0.0
        for player_id in team_b_gives:
            if player_id in all_players:
                player = all_players[player_id]
                scarcity_multiplier = self.position_scarcity.get(player.position, 1.0)
                base_points = self._get_player_projected_points(player_id, all_players)
                adjustment = base_points * (scarcity_multiplier - 1.0)
                team_b_adjustment += adjustment
        
        adjustments['team_a_positional_value'] = team_a_adjustment
        adjustments['team_b_positional_value'] = team_b_adjustment
        adjustments['net_positional_advantage'] = team_a_adjustment - team_b_adjustment
        
        return adjustments
    
    async def _analyze_roster_fit_improvement(
        self,
        team_a_roster: Roster,
        team_a_gives: List[str],
        team_a_receives: List[str],
        team_b_roster: Roster,
        team_b_gives: List[str],
        team_b_receives: List[str],
        league: League,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None
    ) -> RosterFitAnalysis:
        """
        Analyze how the trade improves roster fit for both teams.
        
        Args:
            team_a_roster: Team A's current roster
            team_a_gives: Players team A is trading away
            team_a_receives: Players team A is receiving
            team_b_roster: Team B's current roster
            team_b_gives: Players team B is trading away
            team_b_receives: Players team B is receiving
            league: League information
            all_players: Dictionary of all players
            player_rankings: Optional player rankings data
            
        Returns:
            RosterFitAnalysis with improvement scores
        """
        # Analyze team A improvement
        team_a_before = self._calculate_roster_strength(
            team_a_roster, league, all_players, player_rankings
        )
        team_a_after = self._calculate_roster_strength_after_trade(
            team_a_roster, team_a_gives, team_a_receives, league, all_players, player_rankings
        )
        team_a_improvement = team_a_after - team_a_before
        
        # Analyze team B improvement
        team_b_before = self._calculate_roster_strength(
            team_b_roster, league, all_players, player_rankings
        )
        team_b_after = self._calculate_roster_strength_after_trade(
            team_b_roster, team_b_gives, team_b_receives, league, all_players, player_rankings
        )
        team_b_improvement = team_b_after - team_b_before
        
        # Calculate positional impact
        positional_impact = self._calculate_positional_impact(
            team_a_gives, team_a_receives, team_b_gives, team_b_receives, all_players
        )
        
        # Calculate overall fit score
        overall_fit_score = self._calculate_overall_fit_score(
            team_a_improvement, team_b_improvement, positional_impact
        )
        
        return RosterFitAnalysis(
            team_a_improvement=team_a_improvement,
            team_b_improvement=team_b_improvement,
            positional_impact=positional_impact,
            overall_fit_score=overall_fit_score
        )
    
    def _calculate_roster_strength(
        self,
        roster: Roster,
        league: League,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None
    ) -> float:
        """
        Calculate overall roster strength score.
        
        Args:
            roster: Roster to analyze
            league: League information
            all_players: Dictionary of all players
            player_rankings: Optional player rankings data
            
        Returns:
            Roster strength score (0.0 to 1.0)
        """
        total_strength = 0.0
        roster_positions = league.roster_positions
        
        # Group players by position
        players_by_position = defaultdict(list)
        for player_id in roster.players:
            if player_id in all_players:
                player = all_players[player_id]
                players_by_position[player.position].append(player_id)
        
        # Calculate strength for each position group
        for position in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            position_players = players_by_position.get(position, [])
            required_starters = roster_positions.count(position)
            
            # Add FLEX eligibility for RB/WR/TE
            if position in ['RB', 'WR', 'TE']:
                required_starters += roster_positions.count('FLEX') / 3  # Distribute FLEX among eligible positions
            
            if required_starters > 0:
                position_strength = self._calculate_position_strength(
                    position_players, required_starters, all_players, player_rankings
                )
                weight = self.position_importance.get(position, 0.1)
                total_strength += position_strength * weight
        
        return min(1.0, total_strength)
    
    def _calculate_roster_strength_after_trade(
        self,
        roster: Roster,
        gives: List[str],
        receives: List[str],
        league: League,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None
    ) -> float:
        """
        Calculate roster strength after a hypothetical trade.
        
        Args:
            roster: Current roster
            gives: Players being traded away
            receives: Players being received
            league: League information
            all_players: Dictionary of all players
            player_rankings: Optional player rankings data
            
        Returns:
            Post-trade roster strength score
        """
        # Create hypothetical post-trade roster
        new_players = [p for p in roster.players if p not in gives] + receives
        
        # Create temporary roster object
        temp_roster = Roster(
            roster_id=roster.roster_id,
            owner_id=roster.owner_id,
            league_id=roster.league_id,
            players=new_players,
            starters=roster.starters  # Keep existing starters for simplicity
        )
        
        return self._calculate_roster_strength(temp_roster, league, all_players, player_rankings)
    
    def _calculate_position_strength(
        self,
        player_ids: List[str],
        required_starters: float,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None
    ) -> float:
        """
        Calculate strength at a specific position.
        
        Args:
            player_ids: List of player IDs at this position
            required_starters: Number of required starters
            all_players: Dictionary of all players
            player_rankings: Optional player rankings data
            
        Returns:
            Position strength score (0.0 to 1.0)
        """
        if not player_ids or required_starters <= 0:
            return 0.0
        
        # Get projected points for all players at position
        player_points = []
        for player_id in player_ids:
            points = self._get_player_projected_points(
                player_id, all_players, player_rankings
            )
            player_points.append(points)
        
        # Sort by points (highest first)
        player_points.sort(reverse=True)
        
        # Calculate starter strength
        starter_points = sum(player_points[:int(required_starters)])
        
        # Add partial value for bench depth
        bench_points = sum(player_points[int(required_starters):]) * self.bench_multiplier
        
        total_points = starter_points + bench_points
        
        # Normalize to 0-1 scale (using position-specific maximums)
        position_max_points = required_starters * 200  # Rough maximum per starter
        strength = min(1.0, total_points / position_max_points)
        
        return strength
    
    def _calculate_positional_impact(
        self,
        team_a_gives: List[str],
        team_a_receives: List[str],
        team_b_gives: List[str],
        team_b_receives: List[str],
        all_players: Dict[str, Player]
    ) -> Dict[str, float]:
        """
        Calculate the positional impact of the trade.
        
        Args:
            team_a_gives: Players team A is trading away
            team_a_receives: Players team A is receiving
            team_b_gives: Players team B is trading away
            team_b_receives: Players team B is receiving
            all_players: Dictionary of all players
            
        Returns:
            Dictionary with positional impact scores
        """
        impact = {}
        
        # Analyze impact by position
        for position in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            # Team A impact
            gives_at_pos = sum(1 for pid in team_a_gives 
                             if pid in all_players and all_players[pid].position == position)
            receives_at_pos = sum(1 for pid in team_a_receives 
                                if pid in all_players and all_players[pid].position == position)
            team_a_net = receives_at_pos - gives_at_pos
            
            # Team B impact
            gives_at_pos_b = sum(1 for pid in team_b_gives 
                               if pid in all_players and all_players[pid].position == position)
            receives_at_pos_b = sum(1 for pid in team_b_receives 
                                  if pid in all_players and all_players[pid].position == position)
            team_b_net = receives_at_pos_b - gives_at_pos_b
            
            impact[f"{position}_team_a_net"] = team_a_net
            impact[f"{position}_team_b_net"] = team_b_net
        
        return impact
    
    def _calculate_overall_fit_score(
        self,
        team_a_improvement: float,
        team_b_improvement: float,
        positional_impact: Dict[str, float]
    ) -> float:
        """
        Calculate overall trade fit score.
        
        Args:
            team_a_improvement: Team A's roster improvement
            team_b_improvement: Team B's roster improvement
            positional_impact: Positional impact analysis
            
        Returns:
            Overall fit score (0.0 to 1.0)
        """
        # Base score on mutual improvement
        mutual_improvement = (team_a_improvement + team_b_improvement) / 2
        
        # Bonus for balanced trade (both teams improve)
        if team_a_improvement > 0 and team_b_improvement > 0:
            balance_bonus = 0.2
        else:
            balance_bonus = 0.0
        
        # Calculate positional balance
        position_changes = [abs(v) for k, v in positional_impact.items() if k.endswith('_net')]
        positional_balance = 1.0 - (sum(position_changes) / max(1, len(position_changes) * 2))
        
        overall_score = mutual_improvement + balance_bonus + (positional_balance * 0.1)
        
        return max(0.0, min(1.0, overall_score))
    
    def _calculate_acceptance_probability(
        self,
        fair_value: FairValueAnalysis,
        roster_fit: RosterFitAnalysis,
        positional_adjustments: Dict[str, float]
    ) -> float:
        """
        Calculate the probability that the trade will be accepted.
        
        Args:
            fair_value: Fair value analysis
            roster_fit: Roster fit analysis
            positional_adjustments: Positional adjustment values
            
        Returns:
            Acceptance probability (0.0 to 100.0)
        """
        # Fair value component (closer to 1.0 ratio = higher probability)
        value_ratio = fair_value.value_ratio
        if value_ratio > 1.0:
            value_ratio = 1.0 / value_ratio  # Normalize to 0-1 range
        
        fair_value_score = value_ratio * self.acceptance_factors['fair_value_weight']
        
        # Roster fit component
        fit_score = roster_fit.overall_fit_score * self.acceptance_factors['roster_fit_weight']
        
        # Positional need component
        net_positional = abs(positional_adjustments.get('net_positional_advantage', 0))
        positional_score = max(0, 1.0 - (net_positional / 50.0))  # Normalize large differences
        positional_score *= self.acceptance_factors['positional_need_weight']
        
        # Combine components
        total_score = fair_value_score + fit_score + positional_score
        
        # Convert to percentage and apply sigmoid curve for realistic probabilities
        probability = self._apply_sigmoid_curve(total_score) * 100
        
        return max(5.0, min(95.0, probability))  # Keep within reasonable bounds
    
    def _apply_sigmoid_curve(self, score: float) -> float:
        """
        Apply sigmoid curve to normalize acceptance probability.
        
        Args:
            score: Raw score
            
        Returns:
            Sigmoid-normalized score
        """
        # Sigmoid function: 1 / (1 + e^(-k*(x-0.5)))
        k = 10  # Steepness parameter
        return 1.0 / (1.0 + math.exp(-k * (score - 0.5)))
    
    def _generate_recommendation_and_rationale(
        self,
        fair_value: FairValueAnalysis,
        roster_fit: RosterFitAnalysis,
        acceptance_probability: float,
        positional_adjustments: Dict[str, float],
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> Tuple[str, str]:
        """
        Generate trade recommendation and supporting rationale.
        
        Args:
            fair_value: Fair value analysis
            roster_fit: Roster fit analysis
            acceptance_probability: Calculated acceptance probability
            positional_adjustments: Positional adjustment values
            team_a_gives: Players team A is trading away
            team_b_gives: Players team B is trading away
            all_players: Dictionary of all players
            
        Returns:
            Tuple of (recommendation, rationale)
        """
        # Determine recommendation based on multiple factors
        value_ratio = fair_value.value_ratio
        fit_score = roster_fit.overall_fit_score
        team_a_improvement = roster_fit.team_a_improvement
        
        # Generate recommendation
        if acceptance_probability >= 70 and team_a_improvement > 0.05:
            recommendation = "Accept"
        elif acceptance_probability >= 50 and abs(fair_value.point_differential) <= 20:
            recommendation = "Consider"
        elif acceptance_probability >= 30:
            recommendation = "Counter"
        else:
            recommendation = "Decline"
        
        # Build rationale
        rationale_parts = []
        
        # Fair value assessment
        if abs(fair_value.point_differential) <= 10:
            rationale_parts.append("Trade is fairly balanced in terms of projected points")
        elif fair_value.point_differential > 10:
            rationale_parts.append(f"You receive {fair_value.point_differential:.1f} more projected points")
        else:
            rationale_parts.append(f"You give up {abs(fair_value.point_differential):.1f} more projected points")
        
        # Roster fit assessment
        if team_a_improvement > 0.1:
            rationale_parts.append("Trade significantly improves your roster construction")
        elif team_a_improvement > 0.05:
            rationale_parts.append("Trade provides moderate roster improvement")
        elif team_a_improvement > 0:
            rationale_parts.append("Trade provides slight roster improvement")
        else:
            rationale_parts.append("Trade may weaken your roster construction")
        
        # Positional analysis
        net_positional = positional_adjustments.get('net_positional_advantage', 0)
        if abs(net_positional) > 10:
            if net_positional > 0:
                rationale_parts.append("You gain significant positional value due to scarcity")
            else:
                rationale_parts.append("You lose positional value due to scarcity factors")
        
        # Acceptance probability context
        if acceptance_probability >= 70:
            rationale_parts.append("High likelihood of trade acceptance")
        elif acceptance_probability >= 50:
            rationale_parts.append("Moderate likelihood of trade acceptance")
        else:
            rationale_parts.append("Low likelihood of trade acceptance")
        
        # Player-specific insights
        team_a_positions = [all_players[pid].position for pid in team_a_gives if pid in all_players]
        team_b_positions = [all_players[pid].position for pid in team_b_gives if pid in all_players]
        
        if len(set(team_a_positions)) == 1 and len(set(team_b_positions)) == 1:
            if team_a_positions[0] != team_b_positions[0]:
                rationale_parts.append(f"Positional swap: trading {team_a_positions[0]} for {team_b_positions[0]}")
        
        rationale = ". ".join(rationale_parts) + "."
        
        return recommendation, rationale