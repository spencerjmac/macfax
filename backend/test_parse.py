import requests
import pandas as pd
from io import StringIO
url = "https://www.sports-reference.com/cbb/seasons/2023-polls.html"
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers)
tables = pd.read_html(StringIO(resp.text))
df = tables[0]
school_col = df.columns[0]
week6_cols = [c for c in df.columns if c[0] == 'Week Poll' and c[1] == '6']
if not week6_cols:
    print("NO WEEK 6 COLUMN")
else:
    w6 = week6_cols[0]
    data = df[[school_col, w6]].copy()
    data.columns = ['School', 'Rank']
    data = data.dropna()
    data['Rank'] = pd.to_numeric(data['Rank'], errors='coerce')
    data = data.dropna().sort_values('Rank')
    print(data.head(25))
