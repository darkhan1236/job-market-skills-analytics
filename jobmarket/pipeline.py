"""Chunked ETL, source audit, normalized SQLite and compact analytical Parquet."""
import json
import sqlite3
from collections import Counter
from time import perf_counter
import pandas as pd
import numpy as np
from .config import ROOT, RAW, PROCESSED, OUTPUT, DB, make_dirs
from .skills import extract_skills, role_category, PATTERNS

FACTORS = {'YEARLY': 1, 'MONTHLY': 12, 'WEEKLY': 52, 'BIWEEKLY': 26, 'HOURLY': 2080}

def annualize_salary(frame):
    """USD base salary only; midpoint requires both bounds, no guessed missing bound."""
    med = pd.to_numeric(frame['med_salary'], errors='coerce')
    low = pd.to_numeric(frame['min_salary'], errors='coerce')
    high = pd.to_numeric(frame['max_salary'], errors='coerce')
    midpoint = (low + high) / 2
    value = med.where(med > 0, midpoint.where((low > 0) & (high >= low)))
    valid = frame['currency'].eq('USD') & frame['compensation_type'].eq('BASE_SALARY')
    result = value * frame['pay_period'].map(FACTORS)
    return result.where(valid & np.isfinite(result) & (result > 0))

def clean_chunk(raw, seen):
    ids = pd.to_numeric(raw['job_id'], errors='coerce')
    valid = ids.notna() & ids.gt(0) & ids.eq(ids.round())
    frame = raw.loc[valid].copy()
    frame['job_id'] = ids.loc[valid].astype('int64')
    frame = frame.drop_duplicates('job_id', keep='first')
    frame = frame.loc[~frame['job_id'].isin(seen)].copy()
    seen.update(frame['job_id'].tolist())
    out = pd.DataFrame(index=frame.index)
    out['job_id'] = frame['job_id']
    out['company_id'] = pd.to_numeric(frame['company_id'], errors='coerce').astype('Int64')
    out['title'] = frame['title'].fillna('Unknown').str.strip().replace('', 'Unknown')
    out['location'] = frame['location'].fillna('Unknown').str.strip().replace('', 'Unknown')
    out['region'] = out['location'].str.extract(r',\s*([A-Z]{2})$')[0].fillna('Other / unspecified')
    out['category'] = out['title'].map(role_category)
    out['experience'] = frame['formatted_experience_level'].fillna('Unknown')
    out['work_type'] = frame['formatted_work_type'].fillna('Unknown')
    timestamp = pd.to_numeric(frame['original_listed_time'], errors='coerce').fillna(
        pd.to_numeric(frame['listed_time'], errors='coerce'))
    out['posted_date'] = pd.to_datetime(timestamp, unit='ms', utc=True, errors='coerce').dt.strftime('%Y-%m-%d')
    out['currency'] = frame['currency']
    out['pay_period'] = frame['pay_period']
    out['annual_salary'] = annualize_salary(frame)
    # Missing remote flag means unknown, not on-site.
    out['remote_allowed'] = pd.to_numeric(frame['remote_allowed'], errors='coerce').where(lambda x: x.eq(1)).astype('Int8')
    for column in ['views', 'applies']:
        out[column] = pd.to_numeric(frame[column], errors='coerce').where(lambda x: x.ge(0)).astype('float32')
    out['description_chars'] = frame['description'].fillna('').str.len().astype('int32')
    mentions = []
    for job_id, title, description, skills_desc in frame[['job_id', 'title', 'description', 'skills_desc']].itertuples(index=False, name=None):
        text = ' '.join(str(x) for x in [title, description, skills_desc] if pd.notna(x))
        mentions.extend((int(job_id), 'dict:' + name) for name in extract_skills(text))
    return out, mentions, len(raw) - len(out)

def optimize_types(frame):
    before = int(frame.memory_usage(deep=True).sum())
    for column in ['region', 'category', 'experience', 'work_type', 'currency', 'pay_period', 'posted_date']:
        frame[column] = frame[column].astype('category')
    return before, int(frame.memory_usage(deep=True).sum())

def build_database(chunksize=10000):
    make_dirs()
    if not (RAW / 'postings.csv').exists():
        raise FileNotFoundError('Run python main.py download first.')
    staging = PROCESSED / 'jobs.build.db'
    if staging.exists():
        staging.unlink()
    connection = sqlite3.connect(staging)
    connection.executescript((ROOT / 'sql/schema.sql').read_text(encoding='utf-8'))
    started = perf_counter()
    companies = pd.read_csv(RAW / 'companies/companies.csv', usecols=['company_id', 'name', 'country', 'company_size'])
    companies = companies.drop_duplicates('company_id').copy()
    companies['name'] = companies['name'].fillna('Unknown')
    companies.to_sql('companies', connection, if_exists='append', index=False)
    company_ids = set(companies['company_id'])
    platform = pd.read_csv(RAW / 'mappings/skills.csv')
    skills = [('platform:' + row.skill_abr, row.skill_name, 'platform') for row in platform.itertuples()]
    skills.extend(('dict:' + name, name, 'dictionary') for name in PATTERNS)
    connection.executemany('INSERT INTO skills VALUES (?,?,?)', skills)
    connection.commit()
    audit = {'raw_rows': 0, 'clean_rows': 0, 'dropped_invalid_or_duplicate_id': 0,
             'missing': Counter(), 'dtypes': {}, 'memory_chunks': [], 'chunksize': chunksize}
    seen, frames = set(), []
    for number, chunk in enumerate(pd.read_csv(RAW / 'postings.csv', chunksize=chunksize, low_memory=False), 1):
        audit['raw_rows'] += len(chunk)
        audit['missing'].update(chunk.isna().sum().to_dict())
        audit['dtypes'] = {k: str(v) for k, v in chunk.dtypes.items()}
        clean, mentions, dropped = clean_chunk(chunk, seen)
        clean['company_id'] = clean['company_id'].where(clean['company_id'].isin(company_ids))
        clean.to_sql('jobs', connection, if_exists='append', index=False, chunksize=1000)
        connection.executemany('INSERT OR IGNORE INTO job_skills VALUES (?,?)', mentions)
        connection.commit()
        before, after = optimize_types(clean)
        audit['memory_chunks'].append({'chunk': number, 'rows': len(clean), 'before_bytes': before,
                                       'after_bytes': after, 'raw_bytes': int(chunk.memory_usage(deep=True).sum())})
        frames.append(clean)
        audit['dropped_invalid_or_duplicate_id'] += dropped
        audit['clean_rows'] += len(clean)
        print(f'ETL chunk {number}: {len(clean):,} jobs', flush=True)
    valid_skills = set(platform['skill_abr'])
    orphan_links = 0
    for links in pd.read_csv(RAW / 'jobs/job_skills.csv', chunksize=chunksize):
        valid = links['job_id'].isin(seen) & links['skill_abr'].isin(valid_skills)
        orphan_links += int((~valid).sum())
        rows = [(int(row.job_id), 'platform:' + row.skill_abr) for row in links.loc[valid].itertuples()]
        connection.executemany('INSERT OR IGNORE INTO job_skills VALUES (?,?)', rows)
    connection.commit()
    if connection.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Foreign key violations')
    audit['job_skill_links'] = connection.execute('SELECT COUNT(*) FROM job_skills').fetchone()[0]
    audit['orphan_platform_links_excluded'] = orphan_links
    connection.close()
    clean = pd.concat(frames, ignore_index=True)
    optimize_types(clean)
    clean.to_parquet(PROCESSED / 'jobs.parquet', index=False, compression='zstd')
    clean.to_csv(PROCESSED / 'jobs.csv', index=False)
    staging.replace(DB)
    audit['elapsed_seconds'] = perf_counter() - started
    audit['postings_source_bytes'] = (RAW / 'postings.csv').stat().st_size
    audit['parquet_bytes'] = (PROCESSED / 'jobs.parquet').stat().st_size
    audit['analytical_csv_bytes'] = (PROCESSED / 'jobs.csv').stat().st_size
    audit['raw_missing_pct'] = {k: round(v / audit['raw_rows'] * 100, 3) for k, v in audit['missing'].items()}
    (OUTPUT / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    return audit
