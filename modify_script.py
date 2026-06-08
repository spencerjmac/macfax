with open('backend/analyze_champion_zscores.py', 'r') as f:
    content = f.read()
content = content.replace("for champ in champs:", "for champ in champs:\n        if champ.season.year in [2011, 2014]:\n            continue")
with open('backend/analyze_champion_zscores.py', 'w') as f:
    f.write(content)
