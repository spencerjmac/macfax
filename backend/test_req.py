import requests
import pandas as pd
url = "https://www.sports-reference.com/cbb/seasons/2024-polls.html"
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
tables = pd.read_html(response.text)
print("Success! Tables:", len(tables))
