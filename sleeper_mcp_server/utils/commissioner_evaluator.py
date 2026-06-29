"""
Commissioner trade evaluation engine for fantasy football.

This module provides comprehensive trade fairness analysis and collusion detection
for league commissioners, including weighted scoring systems, pattern recognition,
and detailed evaluation reports.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from datetime import datetime, timedelta
import math

from ..models import (
    Player, Roster, League, User, PlayerRanking
)

logger = logging.getLogger(__name__)


class CommissionerEvaluator:
    """
    Commissioner trade evaluation engine that analyzes trade fairness and detects
    potential collusion patterns for league integrity management.
    """
    
    def __init__(self):
        """Initialize the commissioner evaluator with scoring weights and thresholds."""
        
        # Trade fairness scoring weights (must sum to 1.0)
        self.fairness_weights = {
            'player_value': 0.35,      # Raw player value comparison
            'positional_scarcity': 0.25,  # Position scarcity adjustments
            'roster_fit': 0.20,        # How well players fit each roster
            'recent_performance': 0.10,  # Recent performance trends
            'injury_status': 0.10      # Health and availability
        }
        
        # Position scarcity multipliers for fairness calculation
        self.position_scarcity = {
            'QB': 1.0,
            'RB': 1.4,  # Higher scarcity premium
            'WR': 1.1,
            'TE': 1.6,  # Highest scarcity premium
            'K': 0.6,   # Lower value
            'DEF': 0.7  # Lower value
        }
        
        # Collusion detection thresholds
        self.collusion_thresholds = {
            'extreme_value_imbalance': 0.30,  # >30% value difference
            'roster_dumping_threshold': 0.50,  # >50% of quality players
            'playoff_manipulation_weeks': 3,   # Within 3 weeks of playoffs
            'suspicious_pattern_count': 3,     # 3+ suspicious trades
            'lopsided_history_threshold': 0.25  # 25% of trades heavily favor one side
        }
        
        # Fairness score thresholds
        self.fairness_thresholds = {
            'excellent': 85.0,
            'good': 70.0,
            'fair': 55.0,
            'questionable': 40.0,
            'poor': 25.0
        }
    
    async def evaluate_trade_fairness(
        self,
        team_a_roster: Roster,
        team_a_gives: List[str],
        team_b_roster: Roster,
        team_b_gives: List[str],
        league: League,
        all_players: Dict[str, Player],
        league_users: Dict[str, User],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None,
        scoring_format: str = "half_ppr",
        current_week: int = 1,
        playoff_start_week: int = 14
    ) -> Dict[str, Any]:
        """
        Evaluate trade fairness with comprehensive commissioner analysis.
        
        Args:
            team_a_roster: First team's roster
            team_a_gives: List of player IDs team A is trading away
            team_b_roster: Second team's roster
            team_b_gives: List of player IDs team B is trading away
            league: League information
            all_players: Dictionary of all players
            league_users: Dictionary of league users
            player_rankings: Optional player rankings data
            scoring_format: Scoring format ("ppr" or "half_ppr")
            current_week: Current week number
            playoff_start_week: Week when playoffs start
            
        Returns:
            Dictionary with comprehensive fairness evaluation
        """
        try:
            # Validate trade inputs
            self._validate_trade_inputs(team_a_gives, team_b_gives, all_players)
            
            # Calculate fairness score components
            value_analysis = await self._calculate_value_breakdown(
                team_a_gives, team_b_gives, all_players, player_rankings, scoring_format
            )
            
            positional_analysis = self._calculate_positional_fairness(
                team_a_gives, team_b_gives, all_players
            )
            
            roster_impact = await self._calculate_roster_impact_assessment(
                team_a_roster, team_a_gives, team_b_gives,
                team_b_roster, team_b_gives, team_a_gives,
                league, all_players, player_rankings
            )
            
            performance_analysis = self._analyze_recent_performance(
                team_a_gives, team_b_gives, all_players
            )
            
            injury_analysis = self._analyze_injury_impact(
                team_a_gives, team_b_gives, all_players
            )
            
            # Calculate overall fairness score
            fairness_score = self._calculate_overall_fairness_score(
                value_analysis, positional_analysis, roster_impact,
                performance_analysis, injury_analysis
            )
            
            # Analyze league context
            league_context = self._analyze_league_context(
                team_a_roster, team_b_roster, league, current_week, playoff_start_week
            )
            
            # Generate recommendation and concerns
            recommendation, concerns, confidence = self._generate_commissioner_recommendation(
                fairness_score, value_analysis, league_context, current_week, playoff_start_week
            )
            
            return {
                'fairness_score': fairness_score,
                'value_analysis': value_analysis,
                'positional_analysis': positional_analysis,
                'roster_impact': roster_impact,
                'performance_analysis': performance_analysis,
                'injury_analysis': injury_analysis,
                'league_context': league_context,
                'recommendation': recommendation,
                'concerns': concerns,
                'confidence_level': confidence,
                'evaluation_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error evaluating trade fairness: {e}")
            raise
    
    async def detect_trade_collusion(
        self,
        team_a_roster: Roster,
        team_b_roster: Roster,
        team_a_gives: List[str],
        team_b_gives: List[str],
        league: League,
        all_players: Dict[str, Player],
        league_users: Dict[str, User],
        trade_history: Optional[List[Dict[str, Any]]] = None,
        current_week: int = 1,
        playoff_start_week: int = 14
    ) -> Dict[str, Any]:
        """
        Detect potential collusion patterns in trade proposals.
        
        Args:
            team_a_roster: First team's roster
            team_b_roster: Second team's roster
            team_a_gives: Players team A is trading away
            team_b_gives: Players team B is trading away
            league: League information
            all_players: Dictionary of all players
            league_users: Dictionary of league users
            trade_history: Optional historical trade data
            current_week: Current week number
            playoff_start_week: Week when playoffs start
            
        Returns:
            Dictionary with collusion analysis results
        """
        try:
            risk_factors = []
            
            # Check for extreme value imbalance
            value_imbalance = await self._check_value_imbalance(
                team_a_gives, team_b_gives, all_players
            )
            if value_imbalance['is_suspicious']:
                risk_factors.append(value_imbalance)
            
            # Check for roster dumping patterns
            roster_dumping = self._check_roster_dumping(
                team_a_roster, team_a_gives, team_b_roster, team_b_gives, all_players
            )
            if roster_dumping['is_suspicious']:
                risk_factors.append(roster_dumping)
            
            # Check for playoff manipulation
            playoff_manipulation = self._check_playoff_manipulation(
                team_a_roster, team_b_roster, current_week, playoff_start_week
            )
            if playoff_manipulation['is_suspicious']:
                risk_factors.append(playoff_manipulation)
            
            # Analyze historical trading patterns
            if trade_history:
                historical_patterns = self._analyze_historical_patterns(
                    team_a_roster.owner_id, team_b_roster.owner_id, trade_history
                )
                if historical_patterns['is_suspicious']:
                    risk_factors.append(historical_patterns)
            
            # Check for timing suspicions
            timing_analysis = self._analyze_trade_timing(
                current_week, playoff_start_week, team_a_roster, team_b_roster
            )
            if timing_analysis['is_suspicious']:
                risk_factors.append(timing_analysis)
            
            # Check for competitive balance manipulation
            competitive_manipulation = self._check_competitive_balance_manipulation(
                team_a_roster, team_b_roster, team_a_gives, team_b_gives, all_players, current_week, playoff_start_week
            )
            if competitive_manipulation['is_suspicious']:
                risk_factors.append(competitive_manipulation)
            
            # Check for tanking behavior patterns
            tanking_analysis = self._check_tanking_behavior(
                team_a_roster, team_a_gives, team_b_roster, team_b_gives, all_players, current_week, playoff_start_week
            )
            if tanking_analysis['is_suspicious']:
                risk_factors.append(tanking_analysis)
            
            # Calculate overall collusion risk
            collusion_risk = self._calculate_collusion_risk_level(risk_factors)
            
            # Generate recommendations
            recommendation = self._generate_collusion_recommendation(
                collusion_risk, risk_factors
            )
            
            return {
                'collusion_risk': collusion_risk,
                'risk_factors': risk_factors,
                'value_imbalance_percentage': value_imbalance.get('imbalance_percentage', 0),
                'recommendation': recommendation,
                'investigation_priority': self._determine_investigation_priority(risk_factors),
                'suggested_actions': self._suggest_commissioner_actions(collusion_risk, risk_factors),
                'analysis_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error detecting trade collusion: {e}")
            raise
    
    def _validate_trade_inputs(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> None:
        """Validate trade inputs for commissioner evaluation."""
        if not team_a_gives or not team_b_gives:
            raise ValueError("Both teams must trade at least one player")
        
        for player_id in team_a_gives + team_b_gives:
            if player_id not in all_players:
                raise ValueError(f"Player ID {player_id} not found")
    
    async def _calculate_value_breakdown(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None,
        scoring_format: str = "half_ppr"
    ) -> Dict[str, Any]:
        """Calculate detailed value breakdown for commissioner analysis."""
        team_a_values = []
        team_b_values = []
        
        # Calculate individual player values
        for player_id in team_a_gives:
            value = self._get_player_commissioner_value(
                player_id, all_players, player_rankings, scoring_format
            )
            team_a_values.append({
                'player_id': player_id,
                'player_name': all_players[player_id].full_name if player_id in all_players else 'Unknown',
                'position': all_players[player_id].position if player_id in all_players else 'Unknown',
                'value': value
            })
        
        for player_id in team_b_gives:
            value = self._get_player_commissioner_value(
                player_id, all_players, player_rankings, scoring_format
            )
            team_b_values.append({
                'player_id': player_id,
                'player_name': all_players[player_id].full_name if player_id in all_players else 'Unknown',
                'position': all_players[player_id].position if player_id in all_players else 'Unknown',
                'value': value
            })
        
        team_a_total = sum(p['value'] for p in team_a_values)
        team_b_total = sum(p['value'] for p in team_b_values)
        
        value_differential = team_a_total - team_b_total
        value_ratio = team_a_total / team_b_total if team_b_total > 0 else float('inf')
        
        return {
            'team_a_players': team_a_values,
            'team_b_players': team_b_values,
            'team_a_total_value': team_a_total,
            'team_b_total_value': team_b_total,
            'value_differential': value_differential,
            'value_ratio': value_ratio,
            'imbalance_percentage': abs(value_differential) / max(team_a_total, team_b_total) if max(team_a_total, team_b_total) > 0 else 0
        }
    
    def _get_player_commissioner_value(
        self,
        player_id: str,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None,
        scoring_format: str = "half_ppr"
    ) -> float:
        """Get comprehensive player value for commissioner analysis."""
        if player_rankings and player_id in player_rankings:
            base_value = player_rankings[player_id].projected_points
        else:
            # Fallback to position-based estimates
            if player_id not in all_players:
                return 0.0
            
            player = all_players[player_id]
            position_defaults = {
                'QB': 180.0, 'RB': 120.0, 'WR': 110.0,
                'TE': 90.0, 'K': 80.0, 'DEF': 85.0
            }
            base_value = position_defaults.get(player.position, 50.0)
        
        # Apply position scarcity multiplier
        if player_id in all_players:
            player = all_players[player_id]
            scarcity_multiplier = self.position_scarcity.get(player.position, 1.0)
            
            # Apply injury/status penalties
            if player.status and player.status.value != "Active":
                status_penalty = 0.3 if player.status.value in ["Injured Reserve", "Suspended"] else 0.1
                base_value *= (1.0 - status_penalty)
            
            return base_value * scarcity_multiplier
        
        return base_value
    
    def _calculate_positional_fairness(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> Dict[str, Any]:
        """Calculate positional fairness analysis."""
        position_analysis = {}
        
        # Analyze position distribution
        team_a_positions = defaultdict(int)
        team_b_positions = defaultdict(int)
        
        for player_id in team_a_gives:
            if player_id in all_players:
                pos = all_players[player_id].position
                team_a_positions[pos] += 1
        
        for player_id in team_b_gives:
            if player_id in all_players:
                pos = all_players[player_id].position
                team_b_positions[pos] += 1
        
        # Calculate positional balance score
        all_positions = set(team_a_positions.keys()) | set(team_b_positions.keys())
        position_imbalances = []
        
        for pos in all_positions:
            team_a_count = team_a_positions.get(pos, 0)
            team_b_count = team_b_positions.get(pos, 0)
            imbalance = abs(team_a_count - team_b_count)
            position_imbalances.append(imbalance)
        
        avg_imbalance = sum(position_imbalances) / len(position_imbalances) if position_imbalances else 0
        balance_score = max(0, 1.0 - (avg_imbalance / 2.0))  # Normalize to 0-1
        
        return {
            'team_a_positions': dict(team_a_positions),
            'team_b_positions': dict(team_b_positions),
            'positional_balance_score': balance_score,
            'position_imbalances': position_imbalances,
            'is_positionally_balanced': avg_imbalance <= 1.0
        }
    
    async def _calculate_roster_impact_assessment(
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
    ) -> Dict[str, Any]:
        """Calculate comprehensive roster impact assessment."""
        # Calculate pre-trade roster strengths
        team_a_before = self._calculate_roster_strength_score(
            team_a_roster, league, all_players, player_rankings
        )
        team_b_before = self._calculate_roster_strength_score(
            team_b_roster, league, all_players, player_rankings
        )
        
        # Calculate post-trade roster strengths
        team_a_after = self._calculate_post_trade_roster_strength(
            team_a_roster, team_a_gives, team_a_receives, league, all_players, player_rankings
        )
        team_b_after = self._calculate_post_trade_roster_strength(
            team_b_roster, team_b_gives, team_b_receives, league, all_players, player_rankings
        )
        
        # Calculate improvements
        team_a_improvement = team_a_after - team_a_before
        team_b_improvement = team_b_after - team_b_before
        
        # Analyze competitive balance impact
        strength_gap_before = abs(team_a_before - team_b_before)
        strength_gap_after = abs(team_a_after - team_b_after)
        competitive_balance_impact = strength_gap_before - strength_gap_after
        
        return {
            'team_a_strength_before': team_a_before,
            'team_a_strength_after': team_a_after,
            'team_a_improvement': team_a_improvement,
            'team_b_strength_before': team_b_before,
            'team_b_strength_after': team_b_after,
            'team_b_improvement': team_b_improvement,
            'mutual_improvement': team_a_improvement > 0 and team_b_improvement > 0,
            'competitive_balance_impact': competitive_balance_impact,
            'improves_league_balance': competitive_balance_impact > 0
        }
    
    def _calculate_roster_strength_score(
        self,
        roster: Roster,
        league: League,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None
    ) -> float:
        """Calculate overall roster strength score for commissioner analysis."""
        total_value = 0.0
        position_counts = defaultdict(int)
        
        # Calculate total roster value
        for player_id in roster.players:
            if player_id in all_players:
                player_value = self._get_player_commissioner_value(
                    player_id, all_players, player_rankings
                )
                total_value += player_value
                position_counts[all_players[player_id].position] += 1
        
        # Apply positional balance penalties
        required_positions = ['QB', 'RB', 'WR', 'TE']
        balance_penalty = 0.0
        
        for pos in required_positions:
            if position_counts[pos] < 2:  # Minimum depth requirement
                balance_penalty += 0.1
        
        # Normalize to 0-1 scale
        max_possible_value = len(roster.players) * 150  # Rough maximum per player
        strength_score = (total_value / max_possible_value) * (1.0 - balance_penalty)
        
        return max(0.0, min(1.0, strength_score))
    
    def _calculate_post_trade_roster_strength(
        self,
        roster: Roster,
        gives: List[str],
        receives: List[str],
        league: League,
        all_players: Dict[str, Player],
        player_rankings: Optional[Dict[str, PlayerRanking]] = None
    ) -> float:
        """Calculate roster strength after hypothetical trade."""
        # Create post-trade player list
        new_players = [p for p in roster.players if p not in gives] + receives
        
        # Create temporary roster
        temp_roster = Roster(
            roster_id=roster.roster_id,
            owner_id=roster.owner_id,
            league_id=roster.league_id,
            players=new_players,
            starters=roster.starters
        )
        
        return self._calculate_roster_strength_score(
            temp_roster, league, all_players, player_rankings
        )
    
    def _analyze_recent_performance(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> Dict[str, Any]:
        """Analyze recent performance trends of traded players."""
        # This is a simplified implementation - in a real system,
        # you would analyze actual recent game performance
        
        performance_analysis = {
            'team_a_trending_up': 0,
            'team_a_trending_down': 0,
            'team_b_trending_up': 0,
            'team_b_trending_down': 0,
            'performance_balance_score': 0.5  # Neutral by default
        }
        
        # Placeholder for performance trend analysis
        # In a real implementation, this would analyze recent stats
        
        return performance_analysis
    
    def _analyze_injury_impact(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> Dict[str, Any]:
        """Analyze injury status impact on trade fairness."""
        team_a_injured = 0
        team_b_injured = 0
        
        for player_id in team_a_gives:
            if player_id in all_players:
                player = all_players[player_id]
                if player.status and player.status.value in ["Injured Reserve", "Physically Unable to Perform"]:
                    team_a_injured += 1
        
        for player_id in team_b_gives:
            if player_id in all_players:
                player = all_players[player_id]
                if player.status and player.status.value in ["Injured Reserve", "Physically Unable to Perform"]:
                    team_b_injured += 1
        
        injury_imbalance = abs(team_a_injured - team_b_injured)
        
        return {
            'team_a_injured_players': team_a_injured,
            'team_b_injured_players': team_b_injured,
            'injury_imbalance': injury_imbalance,
            'injury_fairness_score': max(0, 1.0 - (injury_imbalance * 0.2))
        }
    
    def _calculate_overall_fairness_score(
        self,
        value_analysis: Dict[str, Any],
        positional_analysis: Dict[str, Any],
        roster_impact: Dict[str, Any],
        performance_analysis: Dict[str, Any],
        injury_analysis: Dict[str, Any]
    ) -> float:
        """Calculate overall fairness score using weighted components."""
        
        # Value component (0-1 scale)
        value_imbalance = value_analysis['imbalance_percentage']
        value_score = max(0, 1.0 - (value_imbalance / 0.5))  # Penalize >50% imbalance heavily
        
        # Positional component
        positional_score = positional_analysis['positional_balance_score']
        
        # Roster fit component
        roster_score = 0.5  # Base score
        if roster_impact['mutual_improvement']:
            roster_score += 0.3
        if roster_impact['improves_league_balance']:
            roster_score += 0.2
        roster_score = min(1.0, roster_score)
        
        # Performance component
        performance_score = performance_analysis['performance_balance_score']
        
        # Injury component
        injury_score = injury_analysis['injury_fairness_score']
        
        # Calculate weighted total
        total_score = (
            value_score * self.fairness_weights['player_value'] +
            positional_score * self.fairness_weights['positional_scarcity'] +
            roster_score * self.fairness_weights['roster_fit'] +
            performance_score * self.fairness_weights['recent_performance'] +
            injury_score * self.fairness_weights['injury_status']
        )
        
        # Convert to 0-100 scale
        return total_score * 100
    
    def _analyze_league_context(
        self,
        team_a_roster: Roster,
        team_b_roster: Roster,
        league: League,
        current_week: int,
        playoff_start_week: int
    ) -> Dict[str, Any]:
        """Analyze league context for trade evaluation."""
        weeks_to_playoffs = playoff_start_week - current_week
        is_playoff_push = weeks_to_playoffs <= 3
        
        return {
            'current_week': current_week,
            'playoff_start_week': playoff_start_week,
            'weeks_to_playoffs': weeks_to_playoffs,
            'is_playoff_push_period': is_playoff_push,
            'league_size': league.total_rosters,
            'playoff_teams': league.settings.playoff_teams if hasattr(league.settings, 'playoff_teams') else 6
        }
    
    def _generate_commissioner_recommendation(
        self,
        fairness_score: float,
        value_analysis: Dict[str, Any],
        league_context: Dict[str, Any],
        current_week: int,
        playoff_start_week: int
    ) -> Tuple[str, List[str], str]:
        """Generate commissioner recommendation with concerns and confidence."""
        concerns = []
        
        # Determine recommendation based on fairness score
        if fairness_score >= self.fairness_thresholds['excellent']:
            recommendation = "APPROVE"
            confidence = "HIGH"
        elif fairness_score >= self.fairness_thresholds['good']:
            recommendation = "APPROVE"
            confidence = "MEDIUM"
        elif fairness_score >= self.fairness_thresholds['fair']:
            recommendation = "INVESTIGATE"
            confidence = "MEDIUM"
            concerns.append("Trade fairness is borderline - consider additional review")
        elif fairness_score >= self.fairness_thresholds['questionable']:
            recommendation = "INVESTIGATE"
            confidence = "HIGH"
            concerns.append("Trade shows significant fairness concerns")
        else:
            recommendation = "VETO"
            confidence = "HIGH"
            concerns.append("Trade appears highly unfair and potentially harmful to league")
        
        # Add specific concerns based on analysis
        if value_analysis['imbalance_percentage'] > 0.25:
            concerns.append(f"Significant value imbalance: {value_analysis['imbalance_percentage']:.1%}")
        
        if league_context['is_playoff_push_period']:
            concerns.append("Trade occurs during playoff push period - monitor for manipulation")
        
        return recommendation, concerns, confidence
    
    async def _check_value_imbalance(
        self,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> Dict[str, Any]:
        """Check for extreme value imbalance indicating potential collusion."""
        team_a_value = sum(
            self._get_player_commissioner_value(pid, all_players)
            for pid in team_a_gives
        )
        team_b_value = sum(
            self._get_player_commissioner_value(pid, all_players)
            for pid in team_b_gives
        )
        
        if max(team_a_value, team_b_value) == 0:
            imbalance_percentage = 0
        else:
            imbalance_percentage = abs(team_a_value - team_b_value) / max(team_a_value, team_b_value)
        
        is_suspicious = imbalance_percentage > self.collusion_thresholds['extreme_value_imbalance']
        
        return {
            'factor_type': 'VALUE_IMBALANCE',
            'is_suspicious': is_suspicious,
            'severity': 'HIGH' if imbalance_percentage > 0.5 else 'MEDIUM' if is_suspicious else 'LOW',
            'imbalance_percentage': imbalance_percentage,
            'description': f"Trade shows {imbalance_percentage:.1%} value imbalance",
            'evidence': [
                f"Team A trading value: {team_a_value:.1f}",
                f"Team B trading value: {team_b_value:.1f}",
                f"Imbalance: {imbalance_percentage:.1%}"
            ]
        }
    
    def _check_roster_dumping(
        self,
        team_a_roster: Roster,
        team_a_gives: List[str],
        team_b_roster: Roster,
        team_b_gives: List[str],
        all_players: Dict[str, Player]
    ) -> Dict[str, Any]:
        """Check for roster dumping patterns."""
        # Calculate what percentage of quality players each team is trading
        team_a_quality_players = self._count_quality_players(team_a_roster.players, all_players)
        team_b_quality_players = self._count_quality_players(team_b_roster.players, all_players)
        
        team_a_quality_traded = self._count_quality_players(team_a_gives, all_players)
        team_b_quality_traded = self._count_quality_players(team_b_gives, all_players)
        
        team_a_dump_ratio = team_a_quality_traded / max(1, team_a_quality_players)
        team_b_dump_ratio = team_b_quality_traded / max(1, team_b_quality_players)
        
        max_dump_ratio = max(team_a_dump_ratio, team_b_dump_ratio)
        is_suspicious = max_dump_ratio > self.collusion_thresholds['roster_dumping_threshold']
        
        return {
            'factor_type': 'ROSTER_DUMPING',
            'is_suspicious': is_suspicious,
            'severity': 'HIGH' if max_dump_ratio > 0.7 else 'MEDIUM' if is_suspicious else 'LOW',
            'description': f"Team trading {max_dump_ratio:.1%} of quality players",
            'evidence': [
                f"Team A dumping ratio: {team_a_dump_ratio:.1%}",
                f"Team B dumping ratio: {team_b_dump_ratio:.1%}"
            ]
        }
    
    def _count_quality_players(self, player_ids: List[str], all_players: Dict[str, Player]) -> int:
        """Count quality players (starters/high-value players) in a list."""
        quality_count = 0
        for player_id in player_ids:
            if player_id in all_players:
                player = all_players[player_id]
                # Consider QB, RB, WR, TE as quality positions
                if player.position in ['QB', 'RB', 'WR', 'TE']:
                    quality_count += 1
        return quality_count
    
    def _check_playoff_manipulation(
        self,
        team_a_roster: Roster,
        team_b_roster: Roster,
        current_week: int,
        playoff_start_week: int
    ) -> Dict[str, Any]:
        """Check for playoff positioning manipulation."""
        weeks_to_playoffs = playoff_start_week - current_week
        is_suspicious = weeks_to_playoffs <= self.collusion_thresholds['playoff_manipulation_weeks']
        
        return {
            'factor_type': 'PLAYOFF_MANIPULATION',
            'is_suspicious': is_suspicious,
            'severity': 'MEDIUM' if is_suspicious else 'LOW',
            'description': f"Trade occurs {weeks_to_playoffs} weeks before playoffs",
            'evidence': [
                f"Current week: {current_week}",
                f"Playoff start: {playoff_start_week}",
                f"Weeks remaining: {weeks_to_playoffs}"
            ]
        }
    
    def _analyze_historical_patterns(
        self,
        team_a_owner: str,
        team_b_owner: str,
        trade_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze historical trading patterns between teams."""
        # Filter trades between these two teams
        bilateral_trades = [
            trade for trade in trade_history
            if (trade.get('team_a_owner') == team_a_owner and trade.get('team_b_owner') == team_b_owner) or
               (trade.get('team_a_owner') == team_b_owner and trade.get('team_b_owner') == team_a_owner)
        ]
        
        if len(bilateral_trades) < 2:
            return {
                'factor_type': 'HISTORICAL_PATTERN',
                'is_suspicious': False,
                'severity': 'LOW',
                'description': 'Insufficient trade history for pattern analysis',
                'evidence': []
            }
        
        # Analyze if trades consistently favor one team
        team_a_favorable = 0
        team_b_favorable = 0
        
        for trade in bilateral_trades:
            # Simplified analysis - in reality would need detailed value comparison
            if trade.get('favors_team_a', False):
                team_a_favorable += 1
            elif trade.get('favors_team_b', False):
                team_b_favorable += 1
        
        total_trades = len(bilateral_trades)
        imbalance_ratio = abs(team_a_favorable - team_b_favorable) / total_trades
        
        is_suspicious = (
            imbalance_ratio > self.collusion_thresholds['lopsided_history_threshold'] and
            total_trades >= self.collusion_thresholds['suspicious_pattern_count']
        )
        
        return {
            'factor_type': 'HISTORICAL_PATTERN',
            'is_suspicious': is_suspicious,
            'severity': 'HIGH' if imbalance_ratio > 0.5 else 'MEDIUM' if is_suspicious else 'LOW',
            'description': f"Historical trades show {imbalance_ratio:.1%} imbalance",
            'evidence': [
                f"Total bilateral trades: {total_trades}",
                f"Trades favoring team A: {team_a_favorable}",
                f"Trades favoring team B: {team_b_favorable}"
            ]
        }
    
    def _analyze_trade_timing(
        self,
        current_week: int,
        playoff_start_week: int,
        team_a_roster: Roster,
        team_b_roster: Roster
    ) -> Dict[str, Any]:
        """Analyze suspicious timing patterns."""
        weeks_to_playoffs = playoff_start_week - current_week
        
        # Check for suspicious timing (very close to playoffs or trade deadline)
        is_suspicious = weeks_to_playoffs <= 2
        
        return {
            'factor_type': 'SUSPICIOUS_TIMING',
            'is_suspicious': is_suspicious,
            'severity': 'MEDIUM' if is_suspicious else 'LOW',
            'description': f"Trade timing: {weeks_to_playoffs} weeks before playoffs",
            'evidence': [
                f"Current week: {current_week}",
                f"Playoff start: {playoff_start_week}"
            ]
        }
    
    def _calculate_collusion_risk_level(self, risk_factors: List[Dict[str, Any]]) -> str:
        """Calculate overall collusion risk level."""
        if not risk_factors:
            return "LOW"
        
        high_severity_count = sum(1 for factor in risk_factors if factor.get('severity') == 'HIGH')
        medium_severity_count = sum(1 for factor in risk_factors if factor.get('severity') == 'MEDIUM')
        
        if high_severity_count >= 2:
            return "HIGH"
        elif high_severity_count >= 1 or medium_severity_count >= 3:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _generate_collusion_recommendation(
        self,
        collusion_risk: str,
        risk_factors: List[Dict[str, Any]]
    ) -> str:
        """Generate collusion-based recommendation."""
        if collusion_risk == "HIGH":
            return "VETO - High collusion risk detected"
        elif collusion_risk == "MEDIUM":
            return "INVESTIGATE - Moderate collusion concerns"
        else:
            return "MONITOR - Low collusion risk"
    
    def _determine_investigation_priority(self, risk_factors: List[Dict[str, Any]]) -> str:
        """Determine investigation priority level."""
        high_severity_factors = [f for f in risk_factors if f.get('severity') == 'HIGH']
        
        if len(high_severity_factors) >= 2:
            return "URGENT"
        elif len(high_severity_factors) >= 1:
            return "HIGH"
        elif len(risk_factors) >= 2:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _suggest_commissioner_actions(
        self,
        collusion_risk: str,
        risk_factors: List[Dict[str, Any]]
    ) -> List[str]:
        """Suggest specific actions for commissioners."""
        actions = []
        
        if collusion_risk == "HIGH":
            actions.extend([
                "Consider vetoing the trade immediately",
                "Review all recent trades between these teams",
                "Interview both team owners about trade rationale",
                "Check for any external relationships between owners"
            ])
        elif collusion_risk == "MEDIUM":
            actions.extend([
                "Request detailed justification from both teams",
                "Review recent trading history",
                "Monitor future trades between these teams",
                "Consider league vote on trade approval"
            ])
        else:
            actions.extend([
                "Allow trade to proceed",
                "Monitor for future patterns",
                "Document analysis for future reference"
            ])
        
        # Add specific actions based on risk factors
        for factor in risk_factors:
            if factor['factor_type'] == 'VALUE_IMBALANCE' and factor['severity'] == 'HIGH':
                actions.append("Verify player valuations with multiple sources")
            elif factor['factor_type'] == 'ROSTER_DUMPING':
                actions.append("Check if dumping team is still competitive")
            elif factor['factor_type'] == 'PLAYOFF_MANIPULATION':
                actions.append("Review playoff implications of trade")
        
        return list(set(actions))  # Remove duplicates
    
    def _check_competitive_balance_manipulation(
        self,
        team_a_roster: Roster,
        team_b_roster: Roster,
        team_a_gives: List[str],
        team_b_gives: List[str],
        all_players: Dict[str, Player],
        current_week: int,
        playoff_start_week: int
    ) -> Dict[str, Any]:
        """Check for trades that manipulate competitive balance unfairly."""
        # Calculate pre-trade team strengths
        team_a_strength_before = self._calculate_simple_roster_strength(team_a_roster.players, all_players)
        team_b_strength_before = self._calculate_simple_roster_strength(team_b_roster.players, all_players)
        
        # Calculate post-trade team strengths
        team_a_players_after = [p for p in team_a_roster.players if p not in team_a_gives] + team_b_gives
        team_b_players_after = [p for p in team_b_roster.players if p not in team_b_gives] + team_a_gives
        
        team_a_strength_after = self._calculate_simple_roster_strength(team_a_players_after, all_players)
        team_b_strength_after = self._calculate_simple_roster_strength(team_b_players_after, all_players)
        
        # Check if one team becomes significantly stronger while the other becomes weaker
        team_a_change = team_a_strength_after - team_a_strength_before
        team_b_change = team_b_strength_after - team_b_strength_before
        
        # Flag if one team gains significantly while the other loses significantly
        strength_transfer = abs(team_a_change + team_b_change)  # Should be close to 0 for fair trades
        is_suspicious = (
            strength_transfer > 0.3 and  # Significant net strength change
            abs(team_a_change - team_b_change) > 0.4 and  # Large disparity in changes
            (playoff_start_week - current_week) <= 4  # Close to playoffs
        )
        
        severity = 'HIGH' if strength_transfer > 0.5 else 'MEDIUM' if is_suspicious else 'LOW'
        
        return {
            'factor_type': 'COMPETITIVE_BALANCE_MANIPULATION',
            'is_suspicious': is_suspicious,
            'severity': severity,
            'description': f"Trade creates {strength_transfer:.1%} net competitive imbalance",
            'evidence': [
                f"Team A strength change: {team_a_change:+.1%}",
                f"Team B strength change: {team_b_change:+.1%}",
                f"Net strength transfer: {strength_transfer:.1%}",
                f"Weeks to playoffs: {playoff_start_week - current_week}"
            ]
        }
    
    def _check_tanking_behavior(
        self,
        team_a_roster: Roster,
        team_a_gives: List[str],
        team_b_roster: Roster,
        team_b_gives: List[str],
        all_players: Dict[str, Player],
        current_week: int,
        playoff_start_week: int
    ) -> Dict[str, Any]:
        """Check for tanking behavior where a team deliberately weakens their roster."""
        # Calculate value of players being traded
        team_a_gives_value = sum(
            self._get_player_commissioner_value(pid, all_players) for pid in team_a_gives
        )
        team_a_receives_value = sum(
            self._get_player_commissioner_value(pid, all_players) for pid in team_b_gives
        )
        
        team_b_gives_value = sum(
            self._get_player_commissioner_value(pid, all_players) for pid in team_b_gives
        )
        team_b_receives_value = sum(
            self._get_player_commissioner_value(pid, all_players) for pid in team_a_gives
        )
        
        # Check if one team is clearly giving up significantly more value
        team_a_net_loss = team_a_gives_value - team_a_receives_value
        team_b_net_loss = team_b_gives_value - team_b_receives_value
        
        # Flag potential tanking if:
        # 1. One team loses significant value (>40% of what they're giving up)
        # 2. It's late in the season but before playoffs (tanking for draft position)
        # 3. The receiving team gets a disproportionate benefit
        
        max_net_loss = max(team_a_net_loss, team_b_net_loss)
        max_gives_value = max(team_a_gives_value, team_b_gives_value)
        
        if max_gives_value > 0:
            loss_percentage = max_net_loss / max_gives_value
        else:
            loss_percentage = 0
        
        # Tanking is more suspicious late in season but before playoffs
        is_tanking_window = current_week >= 10 and current_week < playoff_start_week
        
        is_suspicious = (
            loss_percentage > 0.4 and  # Losing >40% of trade value
            is_tanking_window and  # In potential tanking window
            max_net_loss > 50  # Significant absolute value loss
        )
        
        if is_suspicious:
            severity = 'HIGH' if loss_percentage > 0.6 else 'MEDIUM'
        else:
            severity = 'LOW'
        
        return {
            'factor_type': 'TANKING_BEHAVIOR',
            'is_suspicious': is_suspicious,
            'severity': severity,
            'description': f"Potential tanking with {loss_percentage:.1%} value loss",
            'evidence': [
                f"Team A net loss: {team_a_net_loss:.1f} points",
                f"Team B net loss: {team_b_net_loss:.1f} points",
                f"Maximum loss percentage: {loss_percentage:.1%}",
                f"Current week: {current_week}",
                f"Is tanking window: {is_tanking_window}"
            ]
        }
    
    def _calculate_simple_roster_strength(
        self,
        player_ids: List[str],
        all_players: Dict[str, Player]
    ) -> float:
        """Calculate a simple roster strength score for competitive balance analysis."""
        total_value = 0.0
        for player_id in player_ids:
            if player_id in all_players:
                value = self._get_player_commissioner_value(player_id, all_players)
                total_value += value
        
        # Normalize by roster size to get average player value
        return total_value / max(len(player_ids), 1)