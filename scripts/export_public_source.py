"""Export an allowlisted source tree without Git history or private evidence.

Default is audit-only. --output must name a new directory. This does not push,
create a remote, include credentials, or copy customer reference/fixture values.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


SYNTHETIC_TESTS = {
    'conftest.py', 'test_connector_contracts.py', 'test_field_checks.py', 'test_report_bindings.py',
    'test_account_policy_contracts.py', 'test_configuration_store.py',
    'test_spider_enum_revalidation.py', 'test_infrastructure_settings.py', 'test_dataset_registry.py',
    'test_dataset_policy.py', 'test_extraction_service.py', 'test_configuration_contracts.py',
}
ROOT_FILES = {'.gitignore', '.dockerignore', 'compose.yaml', 'compose.production.yaml', 'docs/refactor/ROLLOUT.md', 'ARCHITECTURE.md', 'FOREX_SOP_RULES.md',
              'ACCOUNT_OPENING_OFFICIAL_RULES.md', 'SOP_SCORING.md', 'SPATIAL_GROUNDING.md', 'DOCUMENT_FAMILIES.md'}


def allowed(path):
    name = PurePosixPath(path)
    if not name.parts or name.is_absolute() or any(part in {'.', '..'} for part in name.parts) or name.name.startswith('.env') or name.suffix in {'.key', '.pem'}:
        return False
    if path in ROOT_FILES:
        return True
    if name.parts[:2] == ('backend', 'tests'):
        return name.name in SYNTHETIC_TESTS and len(name.parts) == 3
    if name.parts[0] == 'backend':
        return (name.parts[:2] == ('backend', 'app') and name.parts[:3] != ('backend', 'app', 'datasets')) or path in {'backend/Dockerfile', 'backend/requirements.txt'}
    if name.parts[0] == 'frontend':
        return not any(part in {'e2e', 'node_modules', '.next'} for part in name.parts) and name.name not in {'CLAUDE.md', 'AGENTS.md', 'e2e-walkthrough.cjs'}
    if name.parts[0] == 'engine':
        return not any(part in {'samples', 'examples', 'tests', 'outputs'} for part in name.parts) and not name.name.endswith('.example.json') and name.suffix != '.pdf'
    if name.parts[0] in {'docker', 'infra'}:
        return True
    return path in {'scripts/init_dev.py', 'scripts/export_public_source.py', 'scripts/test_export_public_source.py'}


def findings(path, content):
    if path.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.xlsx', '.xls', '.dump', '.zip')):
        return ['binary evidence is outside the source allowlist']
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        return ['source must use UTF-8 encoding before it can be inspected']
    problems = []
    for label, pattern in [
        ('16-digit literal requiring manual review', r'(?<!\d)\d{16}(?!\d)'),
        ('private key material', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        ('credential-shaped value', r'\b(?:sk-[A-Za-z0-9]{20,}|llx-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b'),
        ('private document link requires configuration outside source', r'https?://(?:drive|docs)\.google\.com/'),
    ]:
        if re.search(pattern, text):
            problems.append(label)
    return problems


def export(root, output=None):
    root = Path(root).resolve(strict=True)
    def git(*arguments):
        return subprocess.check_output(['git', '-C', str(root), *arguments])
    revision = git('rev-parse', 'HEAD').decode().strip()
    paths = git('ls-tree', '-r', '-z', '--name-only', revision).decode('utf-8').rstrip('\0').split('\0')
    selected = [path for path in paths if allowed(path)]
    if any('\n' in path for path in selected):
        raise ValueError('Source filenames cannot contain line breaks.')
    blobs = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'],
        input=''.join(f'{revision}:{path}\n' for path in selected).encode('utf-8'), capture_output=True, check=True).stdout
    files, rejected = {}, {}
    position = 0
    for path in selected:
        end = blobs.index(b'\n', position)
        _, kind, size = blobs[position:end].split()
        if kind != b'blob':
            raise ValueError('Source export supports ordinary tracked files only.')
        position = end + 1
        content = blobs[position:position + int(size)]
        position += int(size) + 1
        problems = findings(path, content)
        if problems:
            rejected[path] = problems
        else:
            files[path] = content
    # Public examples contain no customer samples. Private references are
    # imported separately into the immutable organization-scoped registry.
    for filename, dataset_id in [('forex_sample.json', 'forex-sample-v1'), ('account_opening_sample.json', 'account-opening-sample-v1')]:
        value = {'id': dataset_id, 'source_name': 'Empty synthetic reference; import your authorized workbook separately',
                 'sha256': hashlib.sha256(b'empty-synthetic-reference-v1').hexdigest(), 'samples': [], 'rows': []}
        files[f'backend/app/datasets/{filename}'] = (json.dumps(value, indent=2) + '\n').encode()
    files['backend/fixtures/.gitkeep'] = b''
    files['README.md'] = PUBLIC_README.encode('utf-8')
    manifest = {'source_commit': revision, 'history_included': False, 'customer_samples_included': False,
                'files': {path: {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)} for path, content in sorted(files.items())}}
    result = {'source_commit': revision, 'selected_files': len(files), 'excluded_files': len(paths) - sum(allowed(path) for path in paths),
              'selected_bytes': sum(map(len, files.values())), 'blocked': rejected, 'written': False}
    if rejected:
        return result
    if output is not None:
        target = Path(output).resolve()
        if target.exists() or target == root or root.is_relative_to(target):
            raise ValueError('Output must be a new directory outside the source checkout.')
        if target.is_relative_to(root):
            raise ValueError('Output must be outside the source checkout.')
        target.mkdir(parents=False, exist_ok=False)
        for path, content in files.items():
            destination = target / path
            if not destination.resolve().is_relative_to(target):
                raise ValueError('Export path escapes the selected directory.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        (target / 'PUBLIC_SOURCE_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        result['written'] = True
    return result


PUBLIC_README = '''# SQE Document Platform

Python/FastAPI document processing, configurable document profiles, SOP controls,
audited review and Kertas Kerja reports, with a Next.js interface.

Refactoring is in progress. Native compatibility and remaining API services,
browser acceptance, and deployment activation are still tracked separately.
This snapshot is not a completed production release.

This source export deliberately omits customer documents, extraction fixtures,
reference workbook values, browser screenshots, secrets and previous Git history.
Included dataset examples are empty synthetic references. Import authorized
private reference JSON separately; never commit operational data or `.env`.
After migration, `app.configuration.import_datasets --expected-database NAME
--organization ORG --reference-file /private/reference.json` imports an authorized
reference without copying it into the source tree. Supply the database URL through
`REFACTOR_DATABASE_URL`. Existing IDs are immutable; replacements need a new ID.

## Local development

Run `python scripts/init_dev.py` once to generate local credentials. Build and
start the infrastructure/API with Docker Compose, then explicitly initialize
the development database using `python -m app.configuration.initialize
--expected-database sqe` inside the API container before starting workers.
Configure a real provider through Configuration; operational extraction fixtures
are not distributed in this repository.

## Controlled upgrade

Keep the existing application and verified database/object backups available.
Apply configuration migrations explicitly against an explicitly named database;
import configuration history and reference datasets before enabling verified or
normalized configuration reads. Business configuration is never published at
startup. `CONFIGURATION_STORAGE_MODE=legacy` and `DATASET_READ_MODE=bundled` are
compatibility defaults; activate new storage modes only after rehearsal.

Production deployment requires environment-specific secrets, TLS, PostgreSQL,
object storage and Temporal. This source export is not evidence of a completed
production cutover. Existing case configuration pins must be preserved.
Use compose.production.yaml and docs/refactor/ROLLOUT.md for release preparation.
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = export(args.source, args.output)
    print(json.dumps(result, indent=2))
    if result['blocked']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
