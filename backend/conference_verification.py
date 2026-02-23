"""
2025-26 NCAA D1 Conference Memberships Verification

Based on actual conference realignment through 2025-26 season:
"""

CORRECT_CONFERENCES_2025_26 = {
    # Mountain West (MWC) - Added Grand Canyon in 2024
    'MWC': [
        'air-force', 'boise-st', 'boise-state', 'colorado-st', 'colorado-state',
        'fresno-st', 'fresno-state', 'nevada', 'new-mexico',
        'san-diego-st', 'san-diego-state', 'sdsu', 'san-jose-st', 'san-jose-state',
        'unlv', 'utah-st', 'utah-state', 'wyoming',
        'grand-canyon',  # Joined MWC in 2024
    ],
    
    # WAC - Lost Grand Canyon to MWC
    'WAC': [
        'abilene-christian', 'cal-baptist', 'california-baptist',
        'southern-utah', 'stephen-f-austin',
        'tarleton-st', 'tarleton-state', 'ut-arlington',
        'utah-tech', 'utah-valley',
    ],
    
    # WCC - Added Oregon State, Washington State, and Seattle
    'WCC': [
        'gonzaga', 'saint-marys', 'saint-mary-s', "saint-mary's", 'st-marys',
        'san-francisco', 'santa-clara', 'loyola-marymount',
        'pepperdine', 'portland', 'pacific', 'san-diego',
        'oregon-st', 'oregon-state',  # Pac-12 refugee (2024)
        'washington-st', 'washington-state',  # Pac-12 refugee (2024)
        'seattle', 'seattle-u',  # Verify if Seattle U moved to WCC
    ],
}

print("Conference changes needed:")
print("=" * 80)
print("\nGrand Canyon: WAC → MWC (joined 2024)")
print("Seattle: WAC → WCC (verify actual membership)")
print("\n" + "=" * 80)
