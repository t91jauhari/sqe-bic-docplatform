import os
import subprocess
import sys


def test_settings_import_does_not_create_directories():
    script = """
from unittest.mock import patch
with patch('pathlib.Path.mkdir', side_effect=AssertionError('Settings imports must not create directories')):
    import app.settings
print('validated')
"""
    result = subprocess.run([sys.executable, '-c', script], env=os.environ.copy(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'validated'


def test_temporal_namespace_is_an_explicit_environment_setting():
    environment = {**os.environ, 'TEMPORAL_NAMESPACE': 'isolated-test'}
    result = subprocess.run([sys.executable, '-c',
        'from app.settings import settings; print(settings.temporal_namespace)'],
        env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'isolated-test'


def test_empty_temporal_namespace_fails_before_worker_startup():
    result = subprocess.run([sys.executable, '-c', 'import app.settings'],
        env={**os.environ, 'TEMPORAL_NAMESPACE': ' '}, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'TEMPORAL_NAMESPACE must not be empty' in result.stderr


def test_explicit_initializer_creates_sqlite_parent(tmp_path):
    target = tmp_path / 'new-directory' / 'nested' / 'database.sqlite'
    environment = {**os.environ, 'DATABASE_URL': f'sqlite:///{target}'}
    result = subprocess.run([sys.executable, '-c',
        'from app.configuration.initialize import initialize_development; initialize_development(); print("initialized")'],
        env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'initialized'
    assert target.is_file()
