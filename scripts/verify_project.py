"""Integration checks for the real database and Streamlit filters, after main.py all."""
import json
import sqlite3
from pathlib import Path
from streamlit.testing.v1 import AppTest

root=Path(__file__).resolve().parents[1]
summary=json.loads((root/'outputs/summary.json').read_text(encoding='utf-8'))
with sqlite3.connect(root/'data/processed/jobs.db') as connection:
    assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==summary['jobs']
    assert connection.execute('SELECT COUNT(*) FROM skills').fetchone()[0]==67
app=AppTest.from_file(str(root/'app.py'),default_timeout=60).run()
assert not app.exception, [x.message for x in app.exception]
assert app.metric[0].value==f"{summary['jobs']:,}"
app.sidebar.multiselect[2].select('Analytics').run()
assert not app.exception
assert int(app.metric[0].value.replace(',','')) < summary['jobs']
app.sidebar.selectbox[0].select('platform').run()
assert not app.exception
app.sidebar.multiselect[2].unselect('Analytics')
app.sidebar.multiselect[0].select('2023')
app.sidebar.multiselect[1].select('WY')
app.sidebar.multiselect[2].select('Data Engineering')
app.run()
assert not app.exception
assert len(app.warning)>=1
print('Database integrity, row counts, dashboard, role filter, skill source and empty result: OK')
