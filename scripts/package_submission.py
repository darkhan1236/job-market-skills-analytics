"""Package code, compact data and final outputs, excluding the 517 MB source CSV."""
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[1]
archive=root/'deliverables/submission.zip'
files=[]
for path in sorted(root.rglob('*')):
    if not path.is_file():
        continue
    relative=path.relative_to(root)
    if any(p in {'.git','.venv','__pycache__','.pytest_cache','qa'} for p in relative.parts):
        continue
    if relative.parts[:2]==('data','raw') and path.name!='manifest.json':
        continue
    if path.name in {'submission.zip','jobs.csv'} or path.suffix in {'.pyc','.log'}:
        continue
    files.append(path)
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
    for path in files:
        zipped.write(path,path.relative_to(root))
print(f'{archive}: {archive.stat().st_size/1e6:.2f} MB, {len(files)} files')
