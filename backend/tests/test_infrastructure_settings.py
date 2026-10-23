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


def test_explicit_initializer_creates_sqlite_parent(tmp_path):
    target = tmp_path / 'new-directory' / 'nested' / 'database.sqlite'
    environment = {**os.environ, 'DATABASE_URL': f'sqlite:///{target}'}
    result = subprocess.run([sys.executable, '-c',
        'from app.configuration.initialize import initialize_development; initialize_development(); print("initialized")'],
        env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'initialized'
    assert target.is_file()
