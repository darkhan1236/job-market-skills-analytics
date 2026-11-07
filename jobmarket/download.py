"""Pinned public Kaggle archive download and validation."""
import hashlib
import json
import zipfile
import requests
from .config import RAW, SOURCE, VERSION, make_dirs

def download_data():
    make_dirs()
    archive = RAW / f'linkedin-v{VERSION}.zip'
    if not archive.exists() or not zipfile.is_zipfile(archive):
        partial = archive.with_suffix('.part')
        url = f'https://www.kaggle.com/api/v1/datasets/download/arshkon/linkedin-job-postings?datasetVersionNumber={VERSION}'
        with requests.get(url, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            with partial.open('wb') as target:
                for block in response.iter_content(1024 * 1024):
                    target.write(block)
        if not zipfile.is_zipfile(partial):
            raise ValueError('Kaggle returned an invalid ZIP. Download version 13 manually into data/raw.')
        partial.replace(archive)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (RAW / member.filename).resolve()
            if not target.is_relative_to(RAW.resolve()):
                raise ValueError('Unsafe archive path')
            if not target.exists() or target.stat().st_size != member.file_size:
                zipped.extract(member, RAW)
    sha = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    manifest = {'source': SOURCE, 'version': VERSION, 'license': 'CC BY-SA 4.0',
                'archive_bytes': archive.stat().st_size, 'archive_sha256': sha,
                'files': {str(p.relative_to(RAW)): p.stat().st_size for p in sorted(RAW.rglob('*.csv'))}}
    (RAW / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
