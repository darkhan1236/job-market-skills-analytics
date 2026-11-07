PRAGMA foreign_keys = ON;
CREATE TABLE companies (
    company_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT,
    company_size INTEGER
);
CREATE TABLE jobs (
    job_id INTEGER PRIMARY KEY,
    company_id INTEGER REFERENCES companies(company_id),
    title TEXT NOT NULL,
    location TEXT NOT NULL,
    region TEXT NOT NULL,
    category TEXT NOT NULL,
    experience TEXT NOT NULL,
    work_type TEXT NOT NULL,
    posted_date TEXT,
    currency TEXT,
    pay_period TEXT,
    annual_salary REAL CHECK (annual_salary IS NULL OR annual_salary > 0),
    remote_allowed INTEGER CHECK (remote_allowed IS NULL OR remote_allowed = 1),
    views REAL,
    applies REAL,
    description_chars INTEGER
);
CREATE TABLE skills (
    skill_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('platform', 'dictionary'))
);
CREATE TABLE job_skills (
    job_id INTEGER NOT NULL REFERENCES jobs(job_id),
    skill_id TEXT NOT NULL REFERENCES skills(skill_id),
    PRIMARY KEY (job_id, skill_id)
);
CREATE INDEX idx_jobs_date ON jobs(posted_date);
CREATE INDEX idx_jobs_filters ON jobs(region, category, posted_date);
CREATE INDEX idx_jobs_company ON jobs(company_id);
CREATE INDEX idx_skill_jobs ON job_skills(skill_id, job_id);
