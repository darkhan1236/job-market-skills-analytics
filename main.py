"""Console entrypoint: download, build, analyze, documents, all, menu."""
import argparse
import sys
from jobmarket.config import make_dirs

def execute(command, chunksize=10000):
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
    parser.add_argument('command',nargs='?',default='menu',choices=['download','build','analyze','documents','all','menu'])
    parser.add_argument('--chunksize',type=int,default=10000)
    args = parser.parse_args()
    if args.chunksize <= 0:
        parser.error('--chunksize must be positive')
    try:
        if args.command == 'menu':
            menu(args.chunksize)
        else:
            execute(args.command,args.chunksize)
    except Exception as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
