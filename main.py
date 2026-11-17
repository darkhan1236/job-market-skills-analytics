"""Console entrypoint: download, build, analyze, predict, documents, all, menu."""
import argparse
from datetime import date
import sys
from jobmarket.config import make_dirs

def execute(command, chunksize=10000, forecast_date=None, method='linear'):
    make_dirs()
    if command in ('download','all'):
        from jobmarket.download import download_data
        download_data()
    if command in ('build','all'):
        from jobmarket.pipeline import build_database
        build_database(chunksize)
    if command in ('analyze','all'):
        from jobmarket.analysis import run_analysis
        run_analysis()
    if command in ('documents','all'):
        from jobmarket.documents import create_documents
        create_documents()
    if command == 'predict':
        from jobmarket.forecast import METHODS, forecast_day, load_forecast_series
        series = load_forecast_series()
        target = forecast_date or series.index[-1].date()
        result = forecast_day(series, target, METHODS[method])
        print(f"Метод: {result['method']}")
        print(f"История: {result['history_start']} - {result['history_end']} (14 дней)")
        if method == 'linear':
            print('Линейная регрессия обучена: x = номер дня 0..13, y = количество вакансий. Прогноз для дня 14.')
        print(f"Дата прогноза: {result['date']}")
        print(f"Прогноз: {result['forecast']:.2f} вакансии")
        if result['actual'] is not None:
            print(f"Фактически: {result['actual']:.0f}")
            print(f"Абсолютная ошибка: {result['absolute_error']:.2f}")
        else:
            print('Фактическое значение для этой даты отсутствует; ошибка не рассчитывается.')

def menu(chunksize):
    choices = {'1':'download','2':'build','3':'analyze','4':'documents','5':'all'}
    while True:
        print('\n1 Download data | 2 Build SQLite | 3 Analysis | 4 Report and slides | 5 All | 0 Exit')
        choice = input('Choose: ').strip()
        if choice == '0':
            break
        elif choice in choices:
            try:
                execute(choices[choice], chunksize)
            except (OSError, ValueError, RuntimeError) as error:
                print(f'Cannot complete operation: {error}')
        else:
            print('Enter a number from 0 to 5.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',default='menu',choices=['download','build','analyze','predict','documents','all','menu'])
    parser.add_argument('--chunksize',type=int,default=10000)
    parser.add_argument('--date',type=date.fromisoformat,help='Дата прогноза в формате YYYY-MM-DD')
    parser.add_argument('--method',choices=['linear','naive','moving-average'],default='linear')
    args = parser.parse_args()
    if args.chunksize <= 0:
        parser.error('--chunksize must be positive')
    try:
        if args.command == 'menu':
            menu(args.chunksize)
        else:
            execute(args.command,args.chunksize,forecast_date=args.date,method=args.method)
    except Exception as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
