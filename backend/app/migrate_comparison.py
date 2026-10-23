"""Add only the comparison table, preserving existing case/document records.

Run with API/workers stopped: python -m app.migrate_comparison
"""
from .db import DatasetComparison, engine

if __name__ == "__main__":
    DatasetComparison.__table__.create(engine, checkfirst=True)
    print("Dataset comparison table is ready; existing extraction records are unchanged.")
