"""Pinned public Kaggle archive download and validation."""
import hashlib
import json
import zipfile
import requests
from .config import RAW, SOURCE, VERSION, make_dirs

DOWNLOAD_URL = (
    'https://www.kaggle.com/api/v1/datasets/download/arshkon/linkedin-job-postings'
    f'?datasetVersionNumber={VERSION}'
)
REQUIRED_FILES = {
    'postings.csv', 'companies/companies.csv',
    'jobs/job_skills.csv', 'mappings/skills.csv',
}


def manual_download_message(reason):
    return (
        f'{reason}\nИсточник: {SOURCE}\n'
        f'Локальный архив версии {VERSION}: {RAW / f"linkedin-v{VERSION}.zip"}\n'
        'После сохранения архива: .venv\\Scripts\\python.exe main.py all '
        '(из корня проекта). Если источник недоступен, потребуется сохранённый '
        'архив этой версии от участника команды.'
    )


def validate_archive(archive):
    if not zipfile.is_zipfile(archive):
        raise ValueError(manual_download_message('Файл не является корректным ZIP-архивом.'))
    with zipfile.ZipFile(archive) as zipped:
        missing = REQUIRED_FILES - set(zipped.namelist())
        if missing:
            raise ValueError(manual_download_message(
                'В архиве отсутствуют обязательные файлы: ' + ', '.join(sorted(missing))))
        for member in zipped.infolist():
            target = (RAW / member.filename).resolve()
            if not target.is_relative_to(RAW.resolve()):
                raise ValueError('Unsafe archive path')


def fetch_archive(archive):
    partial = archive.with_suffix('.part')
    try:
        with requests.get(DOWNLOAD_URL, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            with partial.open('wb') as target:
                for block in response.iter_content(1024 * 1024):
                    target.write(block)
        validate_archive(partial)
        partial.replace(archive)
    except requests.RequestException as error:
        status = getattr(error.response, 'status_code', None)
        reason = f'Автоматическая загрузка Kaggle завершилась ошибкой HTTP {status}.' if status else 'Kaggle недоступен: ошибка соединения или тайм-аут.'
        raise RuntimeError(manual_download_message(reason)) from error
    finally:
        partial.unlink(missing_ok=True)


def download_data():
    make_dirs()
    archive = RAW / f'linkedin-v{VERSION}.zip'
    if not archive.exists():
        fetch_archive(archive)
    validate_archive(archive)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (RAW / member.filename).resolve()
            if not target.is_relative_to(RAW.resolve()):
                raise ValueError('Unsafe archive path')
            if not target.exists() or target.stat().st_size != member.file_size:
                zipped.extract(member, RAW)
    with archive.open('rb') as source:
        sha = hashlib.file_digest(source, 'sha256').hexdigest()
    manifest = {'source': SOURCE, 'version': VERSION, 'license': 'CC BY-SA 4.0',
                'archive_bytes': archive.stat().st_size, 'archive_sha256': sha,
                'files': {str(p.relative_to(RAW)): p.stat().st_size for p in sorted(RAW.rglob('*.csv'))}}
    (RAW / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
