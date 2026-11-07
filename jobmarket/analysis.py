import json
import sqlite3
import tracemalloc
from time import perf_counter
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
from statsmodels.tsa.seasonal import STL
from .config import DB, PROCESSED, OUTPUT
from .queries import run_queries
from .forecast import evaluate_forecasts

def salary_iqr(values):
    values = values.dropna()
    q1, q3 = values.quantile([.25, .75])
    iqr = q3 - q1
    return float(q1-1.5*iqr), float(q3+1.5*iqr)

def save_figure(name):
    plt.tight_layout()
    plt.savefig(OUTPUT / 'figures' / f'{name}.png', dpi=160, bbox_inches='tight')
    plt.close()

def storage_benchmark():
    """Storage comparison with identical analytical columns and groupby operations."""
    columns = ['job_id', 'region', 'annual_salary']
    def load(kind):
        if kind == 'CSV baseline':
            return pd.read_csv(PROCESSED / 'jobs.csv', usecols=columns)
        elif kind == 'Parquet':
            return pd.read_parquet(PROCESSED / 'jobs.parquet', columns=columns)
        with sqlite3.connect(DB) as connection:
            return pd.read_sql_query('SELECT job_id,region,annual_salary FROM jobs', connection)
    def operation(kind):
        frame = load(kind)
        result = frame.groupby('region', observed=True).agg(jobs=('job_id','count'), salary_mean=('annual_salary','mean'))
        result.index = pd.Index(result.index.to_numpy(dtype=str), dtype='str', name='region')
        return result.sort_index()
    baseline = operation('CSV baseline')
    records = []
    for kind in ['CSV baseline','Parquet','SQLite + Pandas']:
        times = []
        for _ in range(3):
            started = perf_counter()
            actual = operation(kind)
            times.append(perf_counter()-started)
        pd.testing.assert_frame_equal(baseline, actual, check_dtype=False, check_index_type=False, rtol=1e-8)
        tracemalloc.start()
        operation(kind)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        records.append({'approach':kind,'seconds_median_3':float(np.median(times)),
                        'python_peak_mib':peak/1024**2,'equivalent_result':True})
    result = pd.DataFrame(records)
    result.to_csv(OUTPUT / 'tables/storage_benchmark.csv', index=False)
    return result

def run_analysis():
    sns.set_theme(style='whitegrid', palette='deep', font='DejaVu Sans')
    plt.rcParams.update({'figure.figsize': (10,5), 'axes.titlesize': 14})
    tables = run_queries()
    data = pd.read_parquet(PROCESSED / 'jobs.parquet')
    data.describe(include='all').to_csv(OUTPUT / 'tables/descriptive_statistics.csv')
    data.isna().mean().mul(100).sort_values(ascending=False).rename('missing_pct').to_csv(OUTPUT / 'tables/clean_missing.csv')
    salary = data['annual_salary'].dropna()
    low, high = salary_iqr(salary)
    salary_outlier = data['annual_salary'].lt(low) | data['annual_salary'].gt(high)
    data.loc[salary_outlier, ['job_id','title','annual_salary']].to_csv(OUTPUT / 'tables/salary_iqr_outliers.csv', index=False)
    # Outliers remain in the database; charts use a labelled IQR subset.
    display = data.loc[data['annual_salary'].between(max(0,low),high)].copy()
    corr_cols = ['annual_salary','views','applies','description_chars']
    correlation = data[corr_cols].corr(method='spearman')
    correlation.to_csv(OUTPUT / 'tables/spearman_correlation.csv')
    data[corr_cols].notna().astype(int).T.dot(data[corr_cols].notna().astype(int)).to_csv(OUTPUT / 'tables/correlation_pair_counts.csv')
    sns.heatmap(correlation, annot=True, fmt='.2f', vmin=-1, vmax=1, cmap='vlag')
    plt.title('Spearman correlations (pairwise non-missing observations)')
    save_figure('05_correlation')
    top = tables['01_top_dictionary_skills'].head(15).iloc[::-1]
    plt.barh(top['name'], top['jobs'], color='#197c80')
    plt.xlabel('Unique postings with a dictionary mention'); plt.title('Skill mentions across all roles')
    save_figure('01_skills')
    sns.histplot(display['annual_salary'], bins=50, color='#197c80')
    plt.xlabel('Annualized USD base salary'); plt.title(f'Salary distribution (IQR display subset, n={len(display):,})')
    save_figure('02_salary_histogram')
    order = display['region'].value_counts().head(10).index.tolist()
    sns.boxplot(data=display, x='region', y='annual_salary', order=order, color='#85babc', showfliers=False)
    plt.ylabel('Annualized USD base salary'); plt.xlabel('Location suffix region')
    plt.title('Salary by region (10 most frequent regions in IQR subset)')
    save_figure('03_salary_regions')
    roles = data['category'].value_counts()
    plt.barh(roles.index[::-1], roles.values[::-1], color='#197c80')
    plt.xlabel('Unique postings'); plt.title('Title-based role groups (heuristic rules)')
    save_figure('04_roles')
    daily = tables['05_daily_counts']
    series, metrics, predictions, protocol = evaluate_forecasts(daily)
    series.rename('jobs').to_csv(OUTPUT / 'tables/forecast_segment.csv', index_label='date')
    series.resample('W').sum().to_csv(OUTPUT / 'tables/weekly_counts_segment.csv', index_label='week_end')
    monthly = data.assign(date=pd.to_datetime(data['posted_date'].astype('string'), errors='coerce')).set_index('date').resample('MS')['job_id'].count()
    monthly.rename('observed_postings').to_csv(OUTPUT / 'tables/monthly_counts.csv', index_label='month')
    series.plot(label='Observed postings', color='#197c80', alpha=.7)
    series.rolling(7, min_periods=7).mean().plot(label='Trailing 7-day mean', color='#d37740')
    plt.axvline(pd.Timestamp(protocol['test_start']), color='black', linestyle='--', label='Test start')
    plt.ylabel('Postings per day'); plt.title('Longest observed daily segment, boundary days excluded'); plt.legend()
    save_figure('06_time_series')
    decomposition = STL(series, period=7, robust=True).fit()
    decomposed = pd.DataFrame({'observed':series,'trend':decomposition.trend,'seasonal':decomposition.seasonal,'residual':decomposition.resid})
    decomposed.to_csv(OUTPUT / 'tables/stl_decomposition.csv', index_label='date')
    fig, axes = plt.subplots(4,1,figsize=(10,8), sharex=True)
    for ax, column in zip(axes, decomposed):
        ax.plot(decomposed.index, decomposed[column], color='#197c80'); ax.set_ylabel(column)
    axes[0].set_title('STL with weekly period (descriptive, not forecasting features)')
    save_figure('07_decomposition')
    for column in predictions.columns[1:]:
        plt.plot(pd.to_datetime(predictions['date']), predictions[column], marker='o', label=column)
    plt.title('One-day-ahead forecasts on the final 7 observed days'); plt.ylabel('Postings per day'); plt.legend()
    save_figure('08_forecast')
    fig = px.line(daily, x='posted_date', y='jobs', markers=True, title='Observed posting dates across collection snapshots (gaps are unknown)')
    # Missing collection dates remain gaps between snapshots.
    full = daily.assign(posted_date=pd.to_datetime(daily['posted_date'])).set_index('posted_date').asfreq('D').reset_index()
    fig = px.line(full, x='posted_date', y='jobs', title='Observed postings; missing collection days remain gaps')
    fig.update_traces(connectgaps=False)
    fig.write_html(OUTPUT / 'figures/interactive_timeline.html', include_plotlyjs=True)
    regions = data.groupby('region',observed=True)['annual_salary'].agg(['count','median']).sort_values('count',ascending=False)
    regions.to_csv(OUTPUT / 'tables/region_salary_medians.csv')
    summary = {'jobs': len(data), 'salary_n':len(salary), 'salary_coverage_pct':len(salary)/len(data)*100,
               'salary_median_usd_year':float(salary.median()), 'salary_iqr_lower':low,'salary_iqr_upper':high,
               'salary_iqr_outliers':int(salary_outlier.sum()),'salary_display_n':len(display),
               'date_min':str(data['posted_date'].dropna().astype('string').min()),
               'date_max':str(data['posted_date'].dropna().astype('string').max()),
               'observed_days':len(daily),'role_counts':{str(k):int(v) for k,v in roles.items()},
               'top_skill_mentions':tables['01_top_dictionary_skills'].head(10).to_dict(orient='records'),
               'forecast':protocol}
    (OUTPUT / 'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    storage_benchmark()
    return summary
