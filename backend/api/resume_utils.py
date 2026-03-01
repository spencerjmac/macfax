"""
Resume Utilities

Helper functions for NCAA-style resume metrics:
- Quadrant determination based on opponent NET rank and location
- Quality win/bad loss detection
"""

from typing import Literal

# NCAA Quadrant Thresholds
# Format: (Q1_max, Q2_max, Q3_max, Q4_min)
QUADRANT_THRESHOLDS = {
    'H': (30, 75, 160, 161),    # Home games
    'N': (50, 100, 200, 201),   # Neutral site
    'A': (75, 135, 240, 241),   # Away games
}


def get_quadrant(opponent_rank: int, location: Literal['H', 'A', 'N']) -> Literal['Q1', 'Q2', 'Q3', 'Q4']:
    """
    Determine NCAA quadrant for a game based on opponent NET rank and location.
    
    Args:
        opponent_rank: Opponent's NET ranking (1-365)
        location: Game location - 'H' (Home), 'A' (Away), 'N' (Neutral)
    
    Returns:
        Quadrant string: 'Q1', 'Q2', 'Q3', or 'Q4'
    
    NCAA Quadrant Definitions:
        HOME:    Q1(1-30)   Q2(31-75)   Q3(76-160)  Q4(161+)
        NEUTRAL: Q1(1-50)   Q2(51-100)  Q3(101-200) Q4(201+)
        AWAY:    Q1(1-75)   Q2(76-135)  Q3(136-240) Q4(241+)
    """
    if location not in QUADRANT_THRESHOLDS:
        raise ValueError(f"Invalid location: {location}. Must be 'H', 'A', or 'N'")
    
    q1_max, q2_max, q3_max, _ = QUADRANT_THRESHOLDS[location]
    
    if opponent_rank <= q1_max:
        return 'Q1'
    elif opponent_rank <= q2_max:
        return 'Q2'
    elif opponent_rank <= q3_max:
        return 'Q3'
    else:
        return 'Q4'


def is_quality_win(opponent_rank: int, location: Literal['H', 'A', 'N'], won: bool) -> bool:
    """
    Determine if a win is considered "quality" (Q1 or Q2 win).
    
    Args:
        opponent_rank: Opponent's NET ranking
        location: Game location
        won: Whether the team won the game
    
    Returns:
        True if it's a Q1 or Q2 win, False otherwise
    """
    if not won:
        return False
    
    quadrant = get_quadrant(opponent_rank, location)
    return quadrant in ['Q1', 'Q2']


def is_bad_loss(opponent_rank: int, location: Literal['H', 'A', 'N'], won: bool) -> bool:
    """
    Determine if a loss is considered "bad" (Q3 or Q4 loss).
    
    Args:
        opponent_rank: Opponent's NET ranking
        location: Game location
        won: Whether the team won the game
    
    Returns:
        True if it's a Q3 or Q4 loss, False otherwise
    """
    if won:
        return False
    
    quadrant = get_quadrant(opponent_rank, location)
    return quadrant in ['Q3', 'Q4']


def get_quadrant_records(games: list) -> dict:
    """
    Compute quadrant records from a list of games.
    
    Args:
        games: List of game dictionaries with keys:
            - opponent_rank: int
            - location: str ('H', 'A', 'N')
            - won: bool
    
    Returns:
        Dictionary with quadrant records:
        {
            'Q1': {'wins': int, 'losses': int},
            'Q2': {'wins': int, 'losses': int},
            'Q3': {'wins': int, 'losses': int},
            'Q4': {'wins': int, 'losses': int},
        }
    """
    records = {
        'Q1': {'wins': 0, 'losses': 0},
        'Q2': {'wins': 0, 'losses': 0},
        'Q3': {'wins': 0, 'losses': 0},
        'Q4': {'wins': 0, 'losses': 0},
    }
    
    for game in games:
        quadrant = get_quadrant(game['opponent_rank'], game['location'])
        if game['won']:
            records[quadrant]['wins'] += 1
        else:
            records[quadrant]['losses'] += 1
    
    return records


def format_quadrant_record(wins: int, losses: int) -> str:
    """
    Format a quadrant record as a string (e.g., "5-2").
    
    Args:
        wins: Number of wins
        losses: Number of losses
    
    Returns:
        Formatted record string
    """
    return f"{wins}-{losses}"
