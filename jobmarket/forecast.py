"""Expanding-window, one-day-ahead forecasts without future target features."""
import json
import sqlite3
import tracemalloc
from time import perf_counter
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from .config import DB, OUTPUT

METHODS = {'linear': 'Linear regression', 'naive': 'Naive', 'moving-average': 'Moving average 7'}


def load_forecast_series():
    if not DB.exists():
        raise FileNotFoundError('База jobs.db отсутствует. Подготовка: .venv\\Scripts\\python.exe main.py all')
    with sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True) as connection:
        daily = pd.read_sql_query(
            'SELECT posted_date, COUNT(*) AS jobs FROM jobs '
            'WHERE posted_date IS NOT NULL GROUP BY posted_date ORDER BY posted_date', connection)
    return longest_observed_segment(daily)


def forecast_history(series, target_date):
    """Fourteen consecutive observations strictly preceding the target date."""
    target_date = pd.Timestamp(target_date)
    if pd.isna(target_date) or target_date != target_date.normalize():
        raise ValueError('Дата прогноза должна содержать только календарную дату.')
    series = series.copy()
    series.index = pd.DatetimeIndex(pd.to_datetime(series.index))
    if series.index.has_duplicates:
        raise ValueError('Временной ряд содержит повторные даты.')
    history = series.sort_index().loc[lambda s: s.index < target_date].tail(14)
    expected = pd.date_range(end=target_date - pd.Timedelta(days=1), periods=14, freq='D')
    if len(history) != 14 or not history.index.equals(expected):
        raise ValueError('Для прогноза нужны 14 последовательных дней непосредственно перед выбранной датой, без пропусков.')
    values = history.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Количество вакансий должно быть конечным неотрицательным числом.')
    return history


def forecast_day(series, target_date, method='Linear regression'):
    history = forecast_history(series, target_date)
    prediction = predict_next(history.to_numpy(), method)
    indexed = series.copy()
    indexed.index = pd.DatetimeIndex(pd.to_datetime(indexed.index))
    actual = indexed.get(pd.Timestamp(target_date))
    actual = float(actual) if actual is not None and pd.notna(actual) else None
    return {
        'date': str(pd.Timestamp(target_date).date()), 'method': method,
        'history_start': str(history.index[0].date()),
        'history_end': str(history.index[-1].date()), 'history_days': len(history),
        'forecast': prediction, 'actual': actual,
        'absolute_error': abs(prediction - actual) if actual is not None else None,
    }

def longest_observed_segment(daily):
    """Calendar-consecutive observed dates with collection gaps left unfilled."""
    dates = pd.to_datetime(daily['posted_date'])
    if len(dates) == 0:
        raise ValueError('Нет наблюдаемых дат для построения временного ряда.')
    series = pd.Series(daily['jobs'].to_numpy(dtype=float), index=dates).sort_index()
    groups = series.index.to_series().diff().dt.days.ne(1).cumsum()
    segments = [block for _, block in series.groupby(groups.to_numpy())]
    # Selection is independent of forecast errors; potentially partial boundaries are excluded.
    longest = max(segments, key=lambda x: (len(x), x.index[-1]))
    return longest.iloc[1:-1]

def predict_next(history, method):
    history = np.asarray(history, dtype=float)
    if method == 'Naive':
        return float(history[-1])
    elif method == 'Moving average 7':
        return float(history[-7:].mean())
    elif method == 'Linear regression':
        # Fixed 14-day trend window, selected in advance. No target normalization with test data.
        values = history[-14:]
        x = np.arange(len(values)).reshape(-1, 1)
        model = LinearRegression().fit(x, values)
        return max(0.0, float(model.predict([[len(values)]])[0]))
    raise ValueError(f'Unknown method {method}')

def walk_forward(values, start, stop, method):
    return np.array([predict_next(values[:i], method) for i in range(start, stop)])

def evaluate_forecasts(daily):
    series = longest_observed_segment(daily)
    if len(series) < 28:
        raise ValueError(f'Only {len(series)} consecutive interior days. Need >=28 for train/validation/test.')
    values = series.to_numpy()
    horizon = 7
    val_start, test_start = len(values) - 14, len(values) - 7
    records, predictions = [], pd.DataFrame({'date': series.index[test_start:], 'actual': values[test_start:]})
    for method in ['Naive', 'Moving average 7', 'Linear regression']:
        val_pred = walk_forward(values, val_start, test_start, method)
        times = []
        for _ in range(5):
            started = perf_counter()
            test_pred = walk_forward(values, test_start, len(values), method)
            times.append(perf_counter() - started)
        tracemalloc.start()
        walk_forward(values, test_start, len(values), method)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        records.append({'model': method, 'validation_mae': float(np.abs(val_pred-values[val_start:test_start]).mean()),
                        'test_mae': float(np.abs(test_pred-values[test_start:]).mean()),
                        'test_runtime_ms_median_5': float(np.median(times)*1000),
                        'python_peak_kib': peak/1024})
        predictions[method] = test_pred
    metrics = pd.DataFrame(records)
    selected = metrics.sort_values(['validation_mae','model']).iloc[0]['model']
    metadata = {'segment_start': str(series.index[0].date()), 'segment_end': str(series.index[-1].date()),
                'segment_days': len(series), 'train_days': val_start, 'validation_days': horizon,
                'test_days': horizon, 'validation_start': str(series.index[val_start].date()),
                'test_start': str(series.index[test_start].date()), 'selected_on_validation': selected,
                'protocol': 'expanding observations; one-day-ahead; observe actual after each prediction',
                'memory_note': 'tracemalloc peak Python allocations; excludes some native allocations and is not process RSS'}
    metrics.to_csv(OUTPUT / 'tables/forecast_metrics.csv', index=False)
    predictions.to_csv(OUTPUT / 'tables/forecast_predictions.csv', index=False)
    (OUTPUT / 'forecast_protocol.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return series, metrics, predictions, metadata
