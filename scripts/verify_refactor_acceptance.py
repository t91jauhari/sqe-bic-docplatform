"""Read-only saved-case parity against a baseline checkout; prints aggregates only."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, text

CHILD = """
import json,sys
from pathlib import Path
import app
assert Path(app.__file__).resolve().parent == Path(sys.argv[3]).resolve() / 'backend/app'
from app.domain import default_config
from app.configuration.codec import fingerprint
from app.sop import evaluate
from app.transaction_flows import scope_configuration, score_configuration
records=json.loads(Path(sys.argv[1]).read_text())
results=[]
for record in records:
    try:
        cfg=scope_configuration(record['configuration'],record['template'])
        findings=evaluate(record['documents'],cfg,record['context'])
        results.append({'findings':findings,'scores':score_configuration(record['configuration'],record['template'],findings)})
    except (ValueError,KeyError,TypeError) as error:
        results.append({'error':type(error).__name__+':'+str(error)})
Path(sys.argv[2]).write_text(json.dumps({'defaults':fingerprint(default_config()),'cases':results},sort_keys=True,default=str))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--expected-database", required=True)
    args = parser.parse_args()
    baseline = args.baseline.resolve(strict=True)
    current = Path(__file__).resolve().parents[1]
    if baseline == current or not (baseline / "backend/app/sop.py").is_file():
        raise ValueError("Use a separate verified baseline source directory.")
    engine = create_engine(os.environ["REFACTOR_DATABASE_URL"])
    try:
        with engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            if (
                connection.scalar(text("SELECT current_database()"))
                != args.expected_database
            ):
                raise ValueError("Database does not match the explicit target.")

            def digest():
                return {
                    name: connection.scalar(
                        text(
                            f"SELECT md5(COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]')) FROM {name} t"
                        )
                    )
                    for name in ("configurations", "cases", "documents")
                }

            before = digest()
            records = []
            for row in connection.execute(
                text(
                    "SELECT c.id,c.template,cfg.payload,ctx.payload AS context FROM cases c "
                    "JOIN configurations cfg ON cfg.id=c.config_id "
                    "LEFT JOIN case_contexts ctx ON ctx.case_id=c.id ORDER BY c.id"
                )
            ).mappings():
                documents = [
                    dict(doc)
                    for doc in connection.execute(
                        text(
                            "SELECT id,filename,doc_type,status,normalized,validation,raw,overrides FROM documents "
                            "WHERE case_id=:case_id ORDER BY id"
                        ),
                        {"case_id": row["id"]},
                    ).mappings()
                ]
                records.append(
                    {
                        "configuration": row["payload"],
                        "template": row["template"],
                        "context": row["context"] or {},
                        "documents": documents,
                    }
                )
            if not records:
                raise ValueError("The acceptance database has no saved cases.")
            with tempfile.TemporaryDirectory(prefix="sqe-acceptance-") as folder:
                path = Path(folder)
                inputs = path / "inputs.json"
                inputs.write_text(json.dumps(records), encoding="utf-8")
                results = []
                for index, source in enumerate((baseline, current)):
                    env = {
                        **os.environ,
                        "PYTHONPATH": str(source / "backend")
                        + os.pathsep
                        + str(source / "engine"),
                        "APP_ENV": "development",
                        "APP_SECRET": secrets.token_urlsafe(40),
                        "DATABASE_URL": "sqlite://",
                        "STORAGE_DRIVER": "local",
                        "WORKFLOW_DRIVER": "local",
                    }
                    output = path / f"result-{index}.json"
                    subprocess.run(
                        [sys.executable, "-c", CHILD, str(inputs), str(output), str(source)],
                        env=env,
                        cwd=source,
                        check=True,
                    )
                    results.append(json.loads(output.read_text()))
            old, new = results
            differences = sum(a != b for a, b in zip(old["cases"], new["cases"]))
            defaults_equal = old["defaults"] == new["defaults"]
            unchanged = before == digest()
            report = {
                "cases_checked": len(records),
                "findings_checked": sum(
                    len(row.get("findings", [])) for row in new["cases"]
                ),
                "historically_blocked_cases": sum(
                    "error" in row for row in new["cases"]
                ),
                "case_or_score_differences": differences,
                "default_configuration_equal": defaults_equal,
                "source_rows_unchanged": unchanged,
                "provider_calls": 0,
                "writes": False,
            }
            print(json.dumps(report))
            if differences or not defaults_equal or not unchanged:
                raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
