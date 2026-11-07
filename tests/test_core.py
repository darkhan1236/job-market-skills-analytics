import sqlite3
import numpy as np
import pandas as pd
import pytest
from jobmarket.pipeline import annualize_salary
from jobmarket.skills import extract_skills, role_category
from jobmarket.forecast import longest_observed_segment, walk_forward
from jobmarket.queries import load_queries
from jobmarket.config import ROOT

def test_salary_currency_range_and_missing_bounds():
    data=pd.DataFrame({'med_salary':[np.nan,100,50,np.nan,np.nan,0],
        'min_salary':[20,1,1,100,100,100], 'max_salary':[40,2,2,90,np.nan,200],
        'currency':['USD','EUR','USD','USD','USD','USD'],
        'compensation_type':['BASE_SALARY']*6,
        'pay_period':['HOURLY','YEARLY','UNKNOWN','YEARLY','YEARLY','YEARLY']})
    result=annualize_salary(data)
    assert result.iloc[0] == 62400
    assert result.iloc[1:5].isna().all()
    assert result.iloc[5] == 150

def test_skill_boundaries_and_deduplication():
    skills=extract_skills('JavaScript Python python PostgreSQL C++ C# R&D communication')
    assert {'JavaScript','Python','SQL','C++','C#','Communication'} <= set(skills)
    assert 'Java' not in skills and 'R' not in skills
    assert skills.count('Python')==1
    assert role_category('Senior Data Engineer')=='Data Engineering'

def test_no_forecast_leakage():
    first=np.arange(40,dtype=float)+10
    second=first.copy(); second[35:]=1000000
    for method in ['Naive','Moving average 7','Linear regression']:
        np.testing.assert_allclose(walk_forward(first,28,36,method),walk_forward(second,28,36,method))

def test_no_zero_filling_collection_gap():
    daily=pd.DataFrame({'posted_date':['2024-01-01','2024-01-02','2024-02-01','2024-02-02','2024-02-03','2024-02-04'], 'jobs':[1,2,3,4,5,6]})
    segment=longest_observed_segment(daily)
    assert segment.index.tolist()==list(pd.to_datetime(['2024-02-02','2024-02-03']))
    assert segment.tolist()==[4,5]

def test_schema_constraints_and_all_sql():
    connection=sqlite3.connect(':memory:')
    connection.executescript((ROOT/'sql/schema.sql').read_text())
    connection.execute("INSERT INTO companies VALUES (1,'Example','US',1)")
    connection.execute("INSERT INTO jobs(job_id,company_id,title,location,region,category,experience,work_type,posted_date,annual_salary) VALUES (1,1,'Analyst','NY, NY','NY','Analytics','Entry','Full-time','2024-01-01',100000)")
    connection.execute("INSERT INTO skills VALUES ('dict:SQL','SQL','dictionary')")
    connection.execute("INSERT INTO job_skills VALUES (1,'dict:SQL')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO job_skills VALUES (99,'dict:SQL')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO job_skills VALUES (1,'dict:SQL')")
    queries=load_queries()
    assert len(queries)>=8
    for sql in queries.values():
        pd.read_sql_query(sql,connection)
