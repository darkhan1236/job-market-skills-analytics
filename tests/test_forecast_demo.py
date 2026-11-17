"""Interactive one-day predictions use past observations and real model fitting."""
import sqlite3
import numpy as np
import pandas as pd
import pytest
from jobmarket import config, forecast


def example_series():
    return pd.Series(100 + 2*np.arange(40), index=pd.date_range('2024-01-01', periods=40))


def test_regression_fits_exactly_previous_14_days(monkeypatch):
    fits = []
    original = forecast.LinearRegression

    class RecordedRegression(original):
        def fit(self, x, y):
            fits.append((x.copy(), y.copy()))
            return super().fit(x, y)

    monkeypatch.setattr(forecast, 'LinearRegression', RecordedRegression)
    series = example_series()
    result = forecast.forecast_day(series, series.index[20])
    assert result['forecast'] == pytest.approx(140)
    assert result['actual'] == 140
    assert result['absolute_error'] == pytest.approx(0)
    assert len(fits) == 1
    np.testing.assert_array_equal(fits[0][0].ravel(), np.arange(14))
    np.testing.assert_array_equal(fits[0][1], series.iloc[6:20].values)


@pytest.mark.parametrize('method', list(forecast.METHODS.values()))
def test_target_and_future_cannot_change_prediction(method):
    series = example_series()
    first = forecast.forecast_day(series, series.index[20], method)
    changed = series.copy()
    changed.iloc[20:] = 1000000
    second = forecast.forecast_day(changed, series.index[20], method)
    assert first['forecast'] == second['forecast']
    assert first['actual'] != second['actual']


def test_gap_or_insufficient_history_is_rejected():
    series = example_series()
    with pytest.raises(ValueError, match='14'):
        forecast.forecast_day(series, series.index[10])
    with pytest.raises(ValueError, match='14'):
        forecast.forecast_day(series.drop(series.index[19]), series.index[20])


def test_prediction_without_future_actual_has_no_error():
    series = example_series()
    result = forecast.forecast_day(series, series.index[-1] + pd.Timedelta(days=1))
    assert result['forecast'] == pytest.approx(180)
    assert result['actual'] is None and result['absolute_error'] is None


def test_predict_command_uses_same_model(monkeypatch, capsys):
    import main
    monkeypatch.setattr(forecast, 'load_forecast_series', example_series)
    monkeypatch.setattr('sys.argv', ['main.py','predict','--date','2024-01-21','--method','linear'])
    assert main.main() == 0
    output = capsys.readouterr().out
    assert '140.00' in output and '2024-01-21' in output


def test_dashboard_trains_after_click_and_invalidates_old_result(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    db = tmp_path/'jobs.db'
    with sqlite3.connect(db) as connection:
        connection.executescript((config.ROOT/'sql/schema.sql').read_text())
        connection.execute("INSERT INTO skills VALUES ('dict:Python','Python','dictionary')")
        rows = []
        for day, timestamp in enumerate(pd.date_range('2024-01-01',periods=40)):
            for _ in range(10 + 2*day):
                rows.append((len(rows)+1,'Analyst','NY, NY','NY','Analytics','Entry','Full-time',str(timestamp.date()),50000))
        connection.executemany('INSERT INTO jobs(job_id,title,location,region,category,experience,work_type,posted_date,annual_salary) VALUES (?,?,?,?,?,?,?,?,?)',rows)
        connection.execute("INSERT INTO job_skills VALUES (1,'dict:Python')")
    monkeypatch.setattr(config,'DB',db)
    monkeypatch.setattr(config,'OUTPUT',tmp_path)
    app = AppTest.from_file(str(config.ROOT/'app.py'),default_timeout=30).run()
    assert not app.exception
    assert not app.success
    app.button(key='run_forecast').click().run()
    assert not app.exception
    assert app.success
    result = app.session_state['forecast_result'][1]
    assert result['history_days'] == 14
    assert result['forecast'] == pytest.approx(result['actual'])
    labels = {item.label for item in app.metric}
    assert 'Прогноз вакансий' in labels and 'Абсолютная ошибка за день' in labels
    app.selectbox(key='forecast_method').select('Naive').run()
    assert not app.exception and not app.success
    assert 'Прогноз вакансий' not in {item.label for item in app.metric}
    app.button(key='run_forecast').click().run()
    assert not app.exception
    result = app.session_state['forecast_result'][1]
    assert result['absolute_error'] == pytest.approx(2)
