import re
import sqlite3
import pandas as pd
from .config import ROOT, DB, OUTPUT

def load_queries():
    text = (ROOT / 'sql/queries.sql').read_text(encoding='utf-8')
    parts = re.split(r'-- name: ([\w]+)\s*\n', text)
    return {parts[i]: parts[i+1].strip() for i in range(1, len(parts), 2)}

def run_queries():
    results = {}
    with sqlite3.connect(DB) as connection:
        for name, sql in load_queries().items():
            result = pd.read_sql_query(sql, connection)
            result.to_csv(OUTPUT / 'tables' / f'{name}.csv', index=False)
            results[name] = result
    return results
