"""Explicit private baseline import; requires migrated, explicitly named database."""
import argparse
import json
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .dataset_sources import import_bundled
from .datasets import DatasetReference, register_dataset


def read_reference_file(path):
    with open(path, 'rb') as source:
        content = source.read(50 * 1024 * 1024 + 1)
    if len(content) > 50 * 1024 * 1024:
        raise ValueError('Reference JSON exceeds the 50 MB import limit.')
    try:
        return DatasetReference.model_validate(json.loads(content)).model_dump()
    except (ValueError, TypeError):
        raise ValueError('Reference file does not satisfy the dataset contract; values were not logged.') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-database', required=True)
    parser.add_argument('--reference-file', action='append', default=[])
    parser.add_argument('--organization')
    args = parser.parse_args()
    url = os.environ.get('REFACTOR_DATABASE_URL')
    if not url:
        parser.error('Set REFACTOR_DATABASE_URL explicitly.')
    if args.reference_file and not args.organization:
        parser.error('External reference imports require --organization.')
    references = [read_reference_file(path) for path in args.reference_file]
    engine = create_engine(url)
    try:
        if engine.dialect.name != 'postgresql':
            raise ValueError('Baseline import requires PostgreSQL.')
        with Session(engine) as session, session.begin():
            if session.scalar(text('SELECT current_database()')) != args.expected_database:
                raise ValueError('Connected database does not match the explicit target.')
            organizations = list(session.scalars(text('SELECT DISTINCT org FROM configurations ORDER BY org')))
            if args.organization:
                if args.organization not in organizations:
                    raise ValueError('Target organization has no registered configuration.')
                organizations = [args.organization]
            if references:
                count = sum(1 for organization in organizations for reference in references if register_dataset(session, organization, reference))
            else:
                count = sum(len(import_bundled(session, organization)) for organization in organizations)
        print(json.dumps({'organizations': len(organizations), 'datasets_verified': count}))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
