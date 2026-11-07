from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
PROCESSED = ROOT / 'data' / 'processed'
OUTPUT = ROOT / 'outputs'
DB = PROCESSED / 'jobs.db'
SOURCE = 'https://www.kaggle.com/datasets/arshkon/linkedin-job-postings'
VERSION = 13

def make_dirs():
    for path in [RAW, PROCESSED, OUTPUT, OUTPUT / 'figures', OUTPUT / 'tables', ROOT / 'deliverables']:
        path.mkdir(parents=True, exist_ok=True)
