#!/usr/bin/env python3
"""Parse -> Extract -> validate -> Application (23), LLD (36), Invoice (19), Valas 2 (10), Valas 1 (16), eKTP (20) columns."""
import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

import simplejson as json
from dotenv import dotenv_values
from llama_cloud import APIError, LlamaCloud

from schema import COLUMNS, PARSE_PROMPT, SCHEMA, SYSTEM_PROMPT
from validation import validate
from context import check_directory
from profiles import get_profile, PROFILE_NAMES

ROOT = Path(__file__).resolve().parent
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def settings(env_file=None):
    """Explicit --env-file wins; otherwise preserve environment precedence, visibly."""
    path = (env_file or ROOT / ".env").resolve()
    if env_file and not path.is_file():
        raise ValueError(f"Environment file does not exist: {path}")
    values = dotenv_values(path, encoding="utf-8-sig") if path.is_file() else {}
    keys = ["LLAMA_CLOUD_API_KEY", "LLAMA_CLOUD_PROJECT_ID", "LLAMA_CLOUD_ORGANIZATION_ID", "LLAMA_CLOUD_BASE_URL"]
    result = {}
    for key in keys:
        if env_file and key in values:
            value, source = values[key], str(path)
        elif key in os.environ:
            value, source = os.environ[key], "process environment"
        else:
            value, source = values.get(key), str(path)
        result[key] = (value or "").strip()
        if key == "LLAMA_CLOUD_API_KEY":
            print(f"API key source: {source}", flush=True)
            if not env_file and key in os.environ and values.get(key) and os.environ[key].strip() != values[key].strip():
                print("Warning: the environment key differs from .env; the environment key wins. "
                      "Use --env-file .env to select the file explicitly.", flush=True)
    token = result["LLAMA_CLOUD_API_KEY"]
    if not token or token == "your-key-here":
        raise ValueError("Set LLAMA_CLOUD_API_KEY to your real LlamaCloud key in .env or the environment")
    if token.casefold().startswith("bearer "):
        raise ValueError("LLAMA_CLOUD_API_KEY must contain only the key, without 'Bearer '. The SDK adds that header prefix.")
    if any(c.isspace() for c in token) or token.startswith(('"', "'")) or token.endswith(('"', "'")):
        raise ValueError("API key contains whitespace or literal quote characters; copy only the API key value")
    return result


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, use_decimal=True) + "\n", encoding="utf-8")
    temp.replace(path)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), use_decimal=True)


def dump(model):
    return model.model_dump(mode="json", exclude_none=False)


def parse_config(tier, version, document_type="application"):
    profile = get_profile(document_type)
    return {"tier": tier, "version": version,
            "processing_options": {"ocr_parameters": {"languages": ["id", "en"]}, "forms": "enrich"},
            "agentic_options": {"custom_prompt": profile["parse_prompt"]},
            "output_options": {
                "spatial_text": {"preserve_layout_alignment_across_pages": True,
                                 "preserve_very_small_text": True, "do_not_unroll_columns": True},
                "granular_bboxes": ["word", "line", "cell"]}}


def extract_config(tier, version, document_type="application"):
    profile = get_profile(document_type)
    return {"data_schema": profile["schema"], "extraction_target": "per_doc", "tier": tier,
            "version": version, "system_prompt": profile["system_prompt"],
            "cite_sources": True, "confidence_scores": True}


def poll(client, stage, job_id, scope, output, timeout, interval):
    start = time.monotonic()
    previous = None
    while True:
        if stage == "parse":
            result = client.parsing.get(job_id, **scope)
            job = result.job
        else:
            result = client.extract.get(job_id, **scope)
            job = result
        if job.status != previous:
            print(f"{stage}: {job.status} ({job_id})", flush=True)
            previous = job.status
        save(output / f"{stage}_last_response.json", dump(result))
        if job.status in TERMINAL:
            if job.status != "COMPLETED":
                raise RuntimeError(f"{stage} {job.status}: {job.error_message or 'No error detail'}")
            # Expansion is required for evidence; Parse get envelope differs from create.
            if stage == "parse":
                return client.parsing.get(job_id, expand=["forms", "items", "text", "markdown", "metadata"], **scope)
            return client.extract.get(job_id, expand=["extract_metadata", "configuration", "usage"], **scope)
        if time.monotonic() - start >= timeout:
            raise TimeoutError(f"{stage} timed out locally; remote job remains active. Resume with --{stage}-job-id {job_id}")
        time.sleep(min(interval, max(0, timeout - (time.monotonic() - start))))


def cell(key, value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, str):
        return value
    if key in {"beneficiary", "remitter"}:
        return value.get("full_text") or "\n".join(str(value[k]) for k in ["name", "address", "phone"] if value.get(k))
    if key == "beneficiary_bank":
        if not isinstance(value, dict):
            return str(value)
        return "\n".join(str(v) for v in value.values() if v)
    if key in {"transaction_value", "subtotal_all_items", "final_total_amount"} and "amount" in value:
        amount = format(Decimal(str(value["amount"])), "f") if value["amount"] is not None else ""
        return " ".join(x for x in [value.get("currency") or "", amount] if x)
    # Keep compound values and tri-state signature evidence explicit.
    return json.dumps(value, ensure_ascii=False, use_decimal=True)


def export(output, report, columns=None):
    columns = columns or get_profile(report.get("document_type", "application"))["columns"]
    save(output / "validation.json", report)
    save(output / "normalized.json", report["normalized"])
    save(output / "corrections.json", {"applied": report["corrections"],
                                      "suggestions": report["correction_suggestions"],
                                      "checkbox_resolutions": report["checkbox_resolutions"]})
    # Ordered arrays retain duplicate display headers; a JSON object would lose one A/C no.
    rows = [cell(key, report["normalized"][key]) for key, _ in columns]
    save(output / "columns.json", {"headers": [label for _, label in columns],
                                  "keys": [key for key, _ in columns], "row": rows})
    for name, data in [("result.csv", report["normalized"]), ("raw.csv", report["raw"])]:
        with (output / name).open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([label for _, label in columns])
            writer.writerow([cell(key, data[key]) for key, _ in columns])
    if report.get("document_type") == "invoice":
        line_columns = ["row_id", "item_name", "quantity", "quantity_unit", "unit_price", "price_unit", "currency",
                        "printed_subtotal", "computed_subtotal", "difference", "check_status", "other_quantity_note"]
        with (output / "line_items.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(line_columns)
            for item in report["line_items"]:
                writer.writerow([cell(key, item[key]) for key in line_columns])
        save(output / "calculations.json", report["calculations"])
    print(f"Validation: {report['status']}; outputs: {output}")
    for key, info in report["fields"].items():
        if info["issues"]:
            print(f"  {key}: {info['status']} — " + ", ".join(x["code"] for x in info["issues"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-type", choices=PROFILE_NAMES, default="application",
                        help="Select document-specific schema, prompts, sample and policy")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--batch", action="store_true", help="Process *_lld.pdf, *_transaction.pdf, *_invoice.pdf, *_valas2.pdf, *_valas1.pdf *_ektp.pdf and *_riplay.pdf in the samples directory")
    inputs.add_argument("--pdf", type=Path, help="PDF to upload; defaults to the selected profile's included sample")
    inputs.add_argument("--file-id", help="Reuse uploaded dfl-... file")
    inputs.add_argument("--parse-job-id", help="Reuse/resume pjb-... Parse job; no upload or second Parse")
    inputs.add_argument("--extract-job-id", help="Resume ext-... Extract job; no new cloud job")
    inputs.add_argument("--replay", type=Path, help="Offline validation of a saved full extract_response.json")
    parser.add_argument("--policy", type=Path, help="Default: selected document profile's policy.json")
    parser.add_argument("--samples-dir", type=Path, help="Batch input directory; default: samples beside this script")
    parser.add_argument("--application-policy", type=Path, help="Application policy override for batch mode")
    parser.add_argument("--lld-policy", type=Path, help="LLD policy override for batch mode")
    parser.add_argument("--invoice-policy", type=Path, help="Invoice policy override for batch mode")
    parser.add_argument("--riplay-policy", type=Path, help="RIPLAY policy override for batch mode")
    parser.add_argument("--riplay-validation-context", type=Path, help="RIPLAY identity/signature reference context for batch mode")
    parser.add_argument("--ektp-policy", type=Path, help="eKTP policy override for batch mode")
    parser.add_argument("--valas1-policy", type=Path, help="Valas 1 declaration policy override for batch mode")
    parser.add_argument("--valas2-policy", type=Path, help="Valas 2 declaration policy override for batch mode")
    parser.add_argument("--validation-context", type=Path, help="LLD/Invoice history or single-file Valas 1/2 verification or eKTP signature-comparison JSON")
    parser.add_argument("--invoice-validation-context", type=Path, help="Invoice history JSON, forwarded to Invoice documents in batch mode")
    parser.add_argument("--ektp-validation-context", type=Path, help="Trusted signature comparisons, forwarded only to eKTP documents in batch mode")
    parser.add_argument("--valas1-validation-context", type=Path, help="External meterai verification JSON, forwarded only to Valas 1 documents in batch mode")
    parser.add_argument("--valas2-validation-context", type=Path, help="External meterai verification JSON, forwarded only to Valas 2 documents in batch mode")
    parser.add_argument("--name-directory", type=Path, default=ROOT / "name_directory.json",
                        help="Approved bank and branch names/aliases for auditable text correction")
    parser.add_argument("--output", type=Path, help="Default: outputs/<UTC timestamp>")
    parser.add_argument("--parse-tier", choices=["agentic", "agentic_plus", "cost_effective"], default="agentic_plus")
    parser.add_argument("--extract-tier", choices=["agentic", "agentic_plus", "cost_effective"], default="agentic_plus")
    parser.add_argument("--parse-version", default="latest")
    parser.add_argument("--extract-version", default="latest")
    parser.add_argument("--timeout", type=float, default=1200, help="Maximum wait seconds per stage")
    parser.add_argument("--poll-interval", type=float, default=3)
    parser.add_argument("--as-of", type=date.fromisoformat, help="Reference date YYYY-MM-DD; default Jakarta today")
    parser.add_argument("--dry-run", action="store_true", help="Write schema/config only; no cloud calls or key needed")
    parser.add_argument("--env-file", type=Path, help="Use this dotenv file in preference to inherited environment values")
    parser.add_argument("--check-auth", action="store_true", help="Read-only file-list request; no PDF upload, Parse or Extract job")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("--timeout and --poll-interval must be positive")
    if args.batch:
        if args.policy:
            parser.error("Batch mode uses --application-policy, --lld-policy, --invoice-policy, --valas2-policy, --valas1-policy --ektp-policy and --riplay-policy instead of --policy")
        if args.check_auth:
            parser.error("Use --check-auth separately before starting the batch")
        from batch import process_batch
        return process_batch(args, process_document=main)
    if (args.samples_dir or args.application_policy or args.lld_policy or args.invoice_policy
            or args.invoice_validation_context or args.valas2_policy or args.valas2_validation_context
            or args.valas1_policy or args.valas1_validation_context
            or args.ektp_policy or args.ektp_validation_context or args.riplay_policy or args.riplay_validation_context):
        parser.error("--samples-dir and per-profile batch policy/context overrides require --batch")
    profile = get_profile(args.document_type)
    policy = read(args.policy or ROOT / profile["policy"])
    validation_context = read(args.validation_context) if args.validation_context else {}
    if args.validation_context and args.document_type not in {"lld", "invoice", "valas_declaration_2", "valas_declaration_1", "ektp", "riplay"}:
        parser.error("--validation-context applies to LLD, Invoice, Valas 1/2 eKTP and RIPLAY profiles")
    directory = read(args.name_directory)
    check_directory(directory)
    if policy["number_locale"] not in {"id_ID", "en_US"}:
        parser.error("policy.number_locale must be id_ID or en_US")
    output = (args.output or ROOT / "outputs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    parse_options = parse_config(args.parse_tier, args.parse_version, args.document_type)
    extraction_options = extract_config(args.extract_tier, args.extract_version, args.document_type)
    save(output / "schema.json", profile["schema"])
    save(output / "request_config.json", {"document_type": args.document_type, "parse": parse_options, "extract": extraction_options})
    save(output / "policy.json", policy)
    save(output / "name_directory.json", directory)
    if args.document_type in {"lld", "invoice", "valas_declaration_2", "valas_declaration_1", "ektp", "riplay"}:
        save(output / "validation_context.json", validation_context)
    if args.dry_run:
        print(f"Dry run: {args.document_type} schema has {len(profile['columns'])} top-level fields; configs saved to {output}")
        return 0
    if args.replay:
        response = read(args.replay)
        save(output / "extract_response.json", response)
    else:
        config = settings(args.env_file)
        scope = {k: config[e] for k, e in [("project_id", "LLAMA_CLOUD_PROJECT_ID"),
                                          ("organization_id", "LLAMA_CLOUD_ORGANIZATION_ID")] if config[e]}
        kwargs = {"api_key": config["LLAMA_CLOUD_API_KEY"], "timeout": 120.0,
                  # Never automatically retry billable job creation after a lost response.
                  "max_retries": 0}
        if config["LLAMA_CLOUD_BASE_URL"]:
            kwargs["base_url"] = config["LLAMA_CLOUD_BASE_URL"]
        with LlamaCloud(**kwargs) as client:
            print(f"API host: {urlsplit(str(client.base_url)).hostname}; "
                  f"project scope: {'set' if 'project_id' in scope else 'default'}; "
                  f"organization scope: {'set' if 'organization_id' in scope else 'default'}", flush=True)
            if args.check_auth:
                client.files.list(page_size=1, **scope)
                print("Authentication/file-list check passed. No document was uploaded and no processing job was created.")
                return 0
            state = {"scope": scope, "document_type": args.document_type}
            save(output / "state.json", state)
            if args.extract_job_id:
                extract_id = args.extract_job_id
            else:
                if args.parse_job_id:
                    parse_id = args.parse_job_id
                else:
                    if args.file_id:
                        file_id = args.file_id
                    else:
                        pdf = (args.pdf or ROOT / profile["sample"]).resolve()
                        if not pdf.is_file():
                            parser.error(f"PDF does not exist: {pdf}")
                        state.update({"source_file": str(pdf), "source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()})
                        print(f"Uploading {pdf.name}", flush=True)
                        with pdf.open("rb") as f:
                            uploaded = client.files.create(file=f, purpose="parse", **scope)
                        file_id = uploaded.id
                    state["file_id"] = file_id
                    save(output / "state.json", state)
                    created = client.parsing.create(file_id=file_id, **parse_options, **scope)
                    parse_id = created.id
                    save(output / "parse_create_response.json", dump(created))
                state["parse_job_id"] = parse_id
                save(output / "state.json", state)
                parsed = poll(client, "parse", parse_id, scope, output, args.timeout, args.poll_interval)
                save(output / "parse_response.json", dump(parsed))
                if parsed.markdown:
                    (output / "parsed.md").write_text("\n\n".join(page.markdown or "" for page in parsed.markdown.pages), encoding="utf-8")
                # Official v2 glue: pass completed Parse ID, NOT Markdown or the original file ID.
                created = client.extract.create(file_input=parse_id, configuration=extraction_options, **scope)
                extract_id = created.id
                save(output / "extract_create_response.json", dump(created))
            state["extract_job_id"] = extract_id
            save(output / "state.json", state)
            response = dump(poll(client, "extract", extract_id, scope, output, args.timeout, args.poll_interval))
            save(output / "extract_response.json", response)
    if response.get("status") != "COMPLETED":
        raise ValueError("Expected COMPLETED extraction response")
    raw = response.get("extract_result")
    if not isinstance(raw, dict):
        raise ValueError("per_doc extraction did not return an object; inspect extract_response.json")
    save(output / "raw.json", raw)
    save(output / "extract_metadata.json", response.get("extract_metadata"))
    kwargs = {"validation_context": validation_context} if args.document_type in {"lld", "invoice", "valas_declaration_2", "valas_declaration_1", "ektp", "riplay"} else {}
    if args.document_type in {"valas_declaration_2", "valas_declaration_1", "ektp", "riplay"}:
        kwargs["extract_job_id"] = response.get("id")
    report = profile["validate"](raw, response.get("extract_metadata"), policy, args.as_of, directory, **kwargs)
    report.setdefault("document_type", args.document_type)
    export(output, report, profile["columns"])
    # Validation FAIL/REVIEW is a successful extraction; inspect validation.json, not exit code.
    return 0


def error_message(exc):
    """Describe failures without exposing SDK response bodies or credentials."""
    if isinstance(exc, APIError):
        # Server response bodies can contain document text; avoid printing them blindly.
        status = getattr(exc, 'status_code', 'unknown')
        detail = ("Authentication rejected. Confirm the API key source printed above; use --env-file .env "
                  "to bypass an old environment key. Use a current LlamaCloud key without 'Bearer ', "
                  "and ensure its region matches the API host. Test with --check-auth before uploading."
                  if status == 401 else "Check permissions, project scope, region and the saved state.")
        return (f"LlamaCloud API error: {type(exc).__name__}, status={status}. "
                f"{detail} Creation is not automatically retried.")
    if isinstance(exc, (ValueError, RuntimeError, TimeoutError, OSError)):
        return f"Error: {exc}"
    return f"Unexpected {type(exc).__name__}; inspect the saved state and responses."


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (APIError, ValueError, RuntimeError, TimeoutError, OSError) as exc:
        print(error_message(exc), file=sys.stderr)
        sys.exit(1)
