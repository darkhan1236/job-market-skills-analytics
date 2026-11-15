"""Offline archive reuse and failures during dataset preparation."""
import hashlib
import zipfile
from unittest.mock import MagicMock

import pytest
import requests

from jobmarket import download


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    raw = tmp_path / 'data' / 'raw'
    raw.mkdir(parents=True)
    monkeypatch.setattr(download, 'RAW', raw)
    monkeypatch.setattr(download, 'make_dirs', lambda: None)
    return raw


def write_archive(path, extra=None, missing=None):
    with zipfile.ZipFile(path, 'w') as zipped:
        for name in download.REQUIRED_FILES - set(missing or []):
            zipped.writestr(name, 'id\n1\n')
        for name, content in (extra or {}).items():
            zipped.writestr(name, content)


def test_local_archive_prepares_data_without_network(raw_dir, monkeypatch):
    archive = raw_dir / 'linkedin-v13.zip'
    write_archive(archive)

    def no_network(*args, **kwargs):
        pytest.fail('A valid local archive must not contact Kaggle')

    monkeypatch.setattr(download.requests, 'get', no_network)
    manifest = download.download_data()
    assert all((raw_dir / name).exists() for name in download.REQUIRED_FILES)
    assert manifest['version'] == 13
    assert manifest['archive_sha256'] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (raw_dir / 'manifest.json').exists()


def test_http_404_explains_manual_archive_and_cleans_partial(raw_dir, monkeypatch):
    response = requests.Response()
    response.status_code = 404
    partial = raw_dir / 'linkedin-v13.part'
    partial.write_bytes(b'incomplete')

    def unavailable(*args, **kwargs):
        raise requests.HTTPError(response=response)

    monkeypatch.setattr(download.requests, 'get', unavailable)
    with pytest.raises(RuntimeError, match='HTTP 404') as failure:
        download.download_data()
    message = str(failure.value)
    assert str(raw_dir / 'linkedin-v13.zip') in message
    assert download.SOURCE in message
    assert r'.venv\Scripts\python.exe main.py all' in message
    assert not partial.exists()
    assert not (raw_dir / 'linkedin-v13.zip').exists()
    assert not (raw_dir / 'manifest.json').exists()


def test_html_response_is_not_saved_as_dataset(raw_dir, monkeypatch):
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b'<html>Login page</html>']
    monkeypatch.setattr(download.requests, 'get', lambda *a, **k: response)
    with pytest.raises(ValueError, match='ZIP'):
        download.download_data()
    assert not (raw_dir / 'linkedin-v13.zip').exists()
    assert not (raw_dir / 'linkedin-v13.part').exists()


def test_interrupted_transfer_removes_partial(raw_dir, monkeypatch):
    response = MagicMock()
    response.__enter__.return_value = response

    def chunks(*args, **kwargs):
        yield b'partial archive'
        raise requests.ConnectionError('Connection closed')

    response.iter_content.side_effect = chunks
    monkeypatch.setattr(download.requests, 'get', lambda *a, **k: response)
    with pytest.raises(RuntimeError):
        download.download_data()
    assert not (raw_dir / 'linkedin-v13.zip').exists()
    assert not (raw_dir / 'linkedin-v13.part').exists()


@pytest.mark.parametrize('case', ['corrupt', 'wrong_dataset', 'unsafe_path'])
def test_invalid_local_archive_fails_before_extraction(raw_dir, monkeypatch, case):
    archive = raw_dir / 'linkedin-v13.zip'
    if case == 'corrupt':
        archive.write_bytes(b'not a zip')
    elif case == 'wrong_dataset':
        write_archive(archive, missing={'postings.csv'})
    else:
        write_archive(archive, extra={'../../outside.txt': 'unsafe'})
    monkeypatch.setattr(download.requests, 'get', lambda *a, **k: pytest.fail('Unexpected network request'))
    with pytest.raises(ValueError):
        download.download_data()
    assert not (raw_dir / 'postings.csv').exists()
    assert not (raw_dir.parent.parent / 'outside.txt').exists()
    assert not (raw_dir / 'manifest.json').exists()


def test_dashboard_without_database_shows_venv_command(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from jobmarket import config

    monkeypatch.setattr(config, 'DB', tmp_path / 'missing.db')
    app = AppTest.from_file(str(config.ROOT / 'app.py'), default_timeout=30).run()
    assert not app.exception
    assert app.info
    assert app.code[0].value == r'.venv\Scripts\python.exe main.py all'
