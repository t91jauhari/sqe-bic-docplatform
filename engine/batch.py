"""Sequential mixed-document batch with separate summary CSVs per profile."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import re

import run
from profiles import get_profile, PROFILE_NAMES


SUFFIXES = {"_lld.pdf": "lld", "_transaction.pdf": "application", "_invoice.pdf": "invoice",
            "_valas2.pdf": "valas_declaration_2", "_valas1.pdf": "valas_declaration_1", "_ektp.pdf": "ektp", "_riplay.pdf": "riplay"}
META_COLUMNS = ["source_file", "document_type", "processing_status", "validation_status",
                "output_directory", "error", "failed_fields", "review_fields"]


def discover(directory):
    """Only direct children with an explicit supported suffix are uploaded."""
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"Samples directory does not exist: {directory}")
    selected, ignored = [], []
    for path in sorted(directory.iterdir(), key=lambda p: (p.name.casefold(), p.name)):
        if not path.is_file():
            continue
        profile = next((name for suffix, name in SUFFIXES.items() if path.name.casefold().endswith(suffix)), None)
        if profile:
            selected.append((path, profile))
        else:
            ignored.append(path.name)
    return selected, ignored


def safe_stem(path):
    # A numeric prefix prevents collisions even for names differing only in case.
    # Keep readable Unicode filenames while avoiding Windows path punctuation.
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", path.stem).strip(" .")[:100] or "document"


def summary_columns(profile):
    fields = [{"header": key, "key": key, "display_header": label}
              for key, label in get_profile(profile)["columns"]]
    return META_COLUMNS + [field["header"] for field in fields], fields


def checkpoint(output, rows, ignored):
    """Rewrite atomically after each file; preserve identifiers and exact decimals."""
    groups = {}
    for profile in PROFILE_NAMES:
        members = [row for row in rows if row["document_type"] == profile]
        if not members:
            continue
        headers, fields = summary_columns(profile)
        target = output / f"{profile}_result.csv"
        temp = target.with_suffix(".csv.tmp")
        with temp.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, restval="", extrasaction="raise")
            writer.writeheader()
            for row in members:
                cells = {key: row[key] for key in META_COLUMNS}
                cells.update({field["key"]: row.get(f"{profile}.{field['key']}", "") for field in fields})
                writer.writerow(cells)
        temp.replace(target)
        run.save(output / f"{profile}_columns.json", {
            "document_type": profile, "metadata_headers": META_COLUMNS, "fields": fields})
        groups[profile] = {
            "result_csv": target.name, "total_files": len(members),
            "completed": sum(row["processing_status"] == "COMPLETED" for row in members),
            "errors": sum(row["processing_status"] == "ERROR" for row in members),
            "validation_counts": {status: sum(row["validation_status"] == status for row in members)
                                  for status in ["PASS", "FAIL", "REVIEW"]},
        }
    run.save(output / "summary.json", {
        "total_files": len(rows),
        "completed": sum(row["processing_status"] == "COMPLETED" for row in rows),
        "errors": sum(row["processing_status"] == "ERROR" for row in rows),
        "dry_runs": sum(row["processing_status"] == "DRY_RUN" for row in rows),
        "pending": sum(row["processing_status"] == "PENDING" for row in rows),
        "processing": sum(row["processing_status"] == "PROCESSING" for row in rows),
        "interrupted": sum(row["processing_status"] == "INTERRUPTED" for row in rows),
        "validation_counts": {status: sum(row["validation_status"] == status for row in rows)
                              for status in ["PASS", "FAIL", "REVIEW"]},
        "ignored_files": ignored,
        "document_types": groups,
        "documents": [{key: row[key] for key in META_COLUMNS} for row in rows],
    })


def document_arguments(args, source, profile, output):
    argv = ["--document-type", profile, "--pdf", str(source), "--output", str(output)]
    policy = {"lld": args.lld_policy, "application": args.application_policy,
              "invoice": args.invoice_policy, "valas_declaration_2": args.valas2_policy, "valas_declaration_1": args.valas1_policy, "ektp": args.ektp_policy, "riplay": getattr(args, "riplay_policy", None)}[profile]
    context = {"invoice": args.invoice_validation_context, "lld": args.validation_context,
               "valas_declaration_2": args.valas2_validation_context, "valas_declaration_1": args.valas1_validation_context, "ektp": args.ektp_validation_context, "riplay": getattr(args, "riplay_validation_context", None)}.get(profile)
    for flag, value in [
        ("--env-file", args.env_file), ("--name-directory", args.name_directory),
        ("--parse-tier", args.parse_tier), ("--extract-tier", args.extract_tier),
        ("--parse-version", args.parse_version), ("--extract-version", args.extract_version),
        ("--timeout", args.timeout), ("--poll-interval", args.poll_interval),
        ("--as-of", args.as_of),
        ("--policy", policy), ("--validation-context", context),
    ]:
        if value is not None:
            argv.extend([flag, str(value)])
    if args.dry_run:
        argv.append("--dry-run")
    return argv


def process_batch(args, process_document):
    directory = (args.samples_dir or run.ROOT / "samples").resolve()
    selected, ignored = discover(directory)
    if not selected:
        raise ValueError(f"No *_lld.pdf, *_transaction.pdf, *_invoice.pdf, *_valas2.pdf, *_valas1.pdf *_ektp.pdf or *_riplay.pdf files found directly in {directory}")
    output = (args.output or run.ROOT / "outputs" /
              ("batch_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Batch output must be a new or empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, (source, profile) in enumerate(selected, 1):
        relative = Path("documents") / f"{index:04d}_{safe_stem(source)}"
        rows.append({"source_file": source.name, "document_type": profile, "processing_status": "PENDING",
                     "validation_status": "", "output_directory": relative.as_posix(),
                     "error": "", "failed_fields": "", "review_fields": ""})
    run.save(output / "batch_config.json", {
        "samples_directory": str(directory), "parse_tier": args.parse_tier, "extract_tier": args.extract_tier,
        "parse_version": args.parse_version, "extract_version": args.extract_version, "dry_run": args.dry_run,
        "suffix_profiles": SUFFIXES,
    })
    checkpoint(output, rows, ignored)
    print(f"Batch: {len(selected)} matching PDFs; {len(ignored)} other files ignored; outputs: {output}", flush=True)
    interrupted = False
    for index, ((source, profile), row) in enumerate(zip(selected, rows), 1):
        folder = output / row["output_directory"]
        folder.mkdir(parents=True, exist_ok=True)
        run.save(folder / "source.json", {"source_file": source.name, "source_path": str(source), "document_type": profile})
        print(f"[{index}/{len(selected)}] {source.name} -> {profile}", flush=True)
        row["processing_status"] = "PROCESSING"
        checkpoint(output, rows, ignored)
        try:
            code = process_document(document_arguments(args, source, profile, folder))
            if code != 0:
                raise RuntimeError(f"Document runner returned exit code {code}")
            if args.dry_run:
                row["processing_status"] = "DRY_RUN"
            else:
                report = run.read(folder / "validation.json")
                if report.get("document_type") != profile or report.get("status") not in {"PASS", "FAIL", "REVIEW"}:
                    raise ValueError("Document report does not match the selected profile or validation status")
                # Reuse the exact exported cells. Reading JSON numbers back can
                # change their Python type/scale, particularly whole amounts.
                exported = run.read(folder / "columns.json")
                keys = [key for key, _ in get_profile(profile)["columns"]]
                if (exported.get("keys") != keys or len(exported.get("row", [])) != len(keys)
                        or not all(isinstance(value, str) for value in exported["row"])):
                    raise ValueError("Ordered document cells do not match the selected profile")
                cells = {f"{profile}.{key}": value for key, value in zip(keys, exported["row"])}
                failed = ";".join(k for k, info in report["fields"].items() if info["status"] == "FAIL")
                review = ";".join(k for k, info in report["fields"].items() if info["status"] == "REVIEW")
                row.update(cells)
                row.update(processing_status="COMPLETED", validation_status=report["status"],
                           failed_fields=failed, review_fields=review)
        except KeyboardInterrupt:
            interrupted = True
            row.update(processing_status="INTERRUPTED", error="Interrupted; inspect saved job IDs before resubmitting.")
        except SystemExit as exc:
            row.update(processing_status="ERROR", error=f"Document runner exited with code {exc.code}")
        except Exception as exc:
            row.update(processing_status="ERROR", error=run.error_message(exc))
        if row["error"]:
            run.save(folder / "error.json", {"source_file": source.name, "error": row["error"]})
            print(f"  {row['processing_status']}: {row['error']}", flush=True)
        flag_duplicate_invoices(output, rows)
        checkpoint(output, rows, ignored)
        if interrupted:
            break
    completed = sum(row["processing_status"] == "COMPLETED" for row in rows)
    errors = sum(row["processing_status"] == "ERROR" for row in rows)
    results = ", ".join(f"{profile}_result.csv" for profile in PROFILE_NAMES
                        if any(row["document_type"] == profile for row in rows))
    print(f"Batch finished: {completed} completed, {errors} processing errors. Summary CSVs: {results}; outputs: {output}", flush=True)
    # Document FAIL/REVIEW still means processing succeeded, matching single-file behavior.
    return 130 if interrupted else 1 if errors else 0


def flag_duplicate_invoices(output, rows):
    """Mark all completed copies of a duplicate invoice number, without new jobs."""
    groups = {}
    for row in rows:
        if row["document_type"] == "invoice" and row["processing_status"] == "COMPLETED":
            number = row.get("invoice.invoice_number")
            if number and re.fullmatch(r"[A-Za-z0-9_/-]+", number) and any(c.isalnum() for c in number):
                report = run.read(output / row["output_directory"] / "validation.json")
                comparable = number if report["policy"]["invoice_number_case_sensitive"] else number.casefold()
                groups.setdefault(comparable, []).append((row, report))
    for members in groups.values():
        if len(members) < 2:
            continue
        for row, report in members:
            field = report["fields"]["invoice_number"]
            if not any(x["code"] == "DUPLICATE_INVOICE_NUMBER_IN_BATCH" for x in field["issues"]):
                field["issues"].append({"code": "DUPLICATE_INVOICE_NUMBER_IN_BATCH", "severity": "FAIL"})
            field["status"] = report["status"] = "FAIL"
            report["batch_duplicate_sources"] = [member[0]["source_file"] for member in members]
            run.save(output / row["output_directory"] / "validation.json", report)
            row["validation_status"] = "FAIL"
            row["failed_fields"] = ";".join(key for key, info in report["fields"].items() if info["status"] == "FAIL")
            row["review_fields"] = ";".join(key for key, info in report["fields"].items() if info["status"] == "REVIEW")
