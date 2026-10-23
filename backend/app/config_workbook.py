"""Bounded XLSX configuration interchange; import returns a draft, never publishes."""

import copy
import io
import json
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from .sop import fields, approved_scope

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RULE_HEADERS = [
    "id",
    "enabled",
    "source_ref",
    "scope_basis",
    "report_category",
    "operator",
    "left_document",
    "left_field",
    "right_document",
    "right_field",
    "currency_path",
    "other_currency_path",
    "condition_key",
    "condition_operator",
    "condition_value",
    "severity",
    "label",
    "comparison_policy",
]


def export_config(cfg):
    w = Workbook()
    w.remove(w.active)

    def sheet(name, headers, rows):
        s = w.create_sheet(name)
        s.append(headers)
        for row in rows:
            values = [
                    json.dumps(v, ensure_ascii=False)
                    if isinstance(v, (dict, list))
                    else "YES"
                    if v is True
                    else "NO"
                    if v is False
                    else v
                    for v in row
                ]
            if any(isinstance(value, str) and len(value) > 32767 for value in values):
                raise ValueError(f'{name}: a setting exceeds the Excel cell limit; use configuration JSON export.')
            s.append(values)
        for c in s[1]:
            c.font = Font(color="FFFFFF", bold=True)
            c.fill = PatternFill("solid", fgColor="17344A")
        s.freeze_panes = "A2"
        s.auto_filter.ref = s.dimensions
        for i in range(1, len(headers) + 1):
            s.column_dimensions[get_column_letter(i)].width = 30
        # OCR/prompt text must remain literal, never a spreadsheet formula.
        for row in s.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    c.data_type = "s"
        return s

    sheet(
        "Read Me",
        ["Topic", "Instruction"],
        [
            [
                "Import",
                "Upload in Configuration → Automation. Validate and replay draft, then publish. Import never changes active cases.",
            ],
            [
                "Scope",
                "Only listed YES controls and SOP3 system checks; CCTV and external verification cannot be enabled.",
            ],
            [
                "Editing",
                "Use document then field dropdown. Stable field keys refer to normalized engine output.",
            ],
            [
                "Policy",
                "Unresolved data checks fail; only visual checks await review. Signature consistency requires reviewed page/region evidence.",
            ],
            [
                "Round trip",
                "Start with current exported workbook. Edit Workflow, Document Profiles, SOP Rules, Case Templates and Report Context. Other sheets are reference only.",
            ],
        ],
    )
    sheet(
        "General Settings",
        ["key", "value"],
        [
            [k, cfg.get(k, {}) if k in {"forex_sop_policy", "document_families", "customer_aliases", "suffix_aliases", "sop_message_templates"}
             else cfg.get(k, []) if k == "grouping_prefixes"
             else cfg.get(k, "PASS") if k == "sop_review_bypass_result"
             else cfg[k]]
            for k in [
                "provider",
                "maker_checker",
                "extract_version",
                "report_title",
                "name_directory",
                "customer_aliases",
                "sop_review_bypass",
                "sop_review_bypass_result",
                "sequential_page_extraction",
                "cross_page_reference",
                "grouping_prefixes",
                "suffix_aliases",
                "sop_message_templates",
                "forex_sop_policy",
            ] + (['report_definitions'] if 'report_definitions' in cfg else [])
        ],
    )
    family_rows=[]
    for key,value in cfg.get('document_families',{}).items():
        if len(json.dumps(value,ensure_ascii=False))>32767:
            raise ValueError(f'{key}: family configuration exceeds the Excel cell limit; use configuration JSON export.')
        family_rows.append([key,value])
    sheet('Document Families',['family_id','configuration_json'],family_rows)
    sheet(
        "Workflow",
        [
            "order",
            "step_id",
            "action",
            "enabled",
            "preset",
            "parameters_json",
            "timeout_seconds",
            "read_poll_retries",
            "on_error",
        ],
        [
            [
                s.get(k) if k != "parameters_json" else s["parameters"]
                for k in [
                    "order",
                    "step_id",
                    "action",
                    "enabled",
                    "preset",
                    "parameters_json",
                    "timeout_seconds",
                    "read_poll_retries",
                    "on_error",
                ]
            ]
            for s in cfg["workflow"]
        ],
    )
    sheet(
        "Document Profiles",
        [
            "document_type",
            "label",
            "suffixes_json",
            "parse_prompt",
            "system_prompt",
            "policy_json",
            "system_instruction",
            "field_checks_json",
        ],
        [
            [
                name,
                p["label"],
                p["suffixes"],
                p["parse_prompt"],
                p["system_prompt"],
                p["policy"],
                p.get("system_instruction", ""),
                p.get("field_checks"),
            ]
            for name, p in cfg["profiles"].items()
        ],
    )
    rules = []
    for r in cfg["sop_rules"]:
        row = dict(r)
        for key, prefix in [("path", "left"), ("other_path", "right")]:
            parts = (r.get(key) or "").split(".", 1)
            row[prefix + "_document"] = parts[0]
            row[prefix + "_field"] = parts[1] if len(parts) == 2 else ""
        rules.append([row.get(k, "") for k in RULE_HEADERS])
    rs = sheet("SOP Rules", RULE_HEADERS, rules)
    sheet(
        "Case Templates",
        ["id", "label", "required_json"],
        [[k, v["label"], v["required"]] for k, v in cfg["templates"].items()],
    )
    sheet(
        "Transaction Flows",
        [
            "id",
            "description",
            "enabled_json",
            "sop_rule_ids_json",
            "document_family",
            "dataset_id",
            "report_layout",
            "report_context_json",
        ],
        [
            [
                k,
                v.get("description", ""),
                json.dumps(v.get("enabled", True)),
                v.get("sop_rule_ids"),
                v.get("document_family"),
                v.get("dataset_id"),
                v.get("report_layout"),
                v.get("report_context"),
            ]
            for k, v in cfg["templates"].items()
        ],
    )
    sheet("Report Context", ["key", "value"], list(cfg["report_context"].items()))
    sheet(
        "Field Catalog",
        ["document", "field", "path", "label", "type"],
        [
            [f[k] for k in ["document", "field", "path", "label", "type"]]
            for f in fields()
        ],
    )
    scope = approved_scope()
    sheet("SOP Scope", list(scope[0]), [[r.get(k) for k in scope[0]] for r in scope])
    lists = w.create_sheet("Lists")
    lists.sheet_state = "hidden"
    for col, doc in enumerate(cfg["profiles"], 1):
        vals = [f["field"] for f in fields() if f["document"] == doc]
        for row, v in enumerate(vals, 2):
            lists.cell(row, col, v)
        letter = get_column_letter(col)
        w.defined_names.add(
            DefinedName(
                "Fields_" + doc,
                attr_text=f"'Lists'!${letter}$2:${letter}${len(vals) + 1}",
            )
        )

    def dropdown(col, formula):
        d = DataValidation(type="list", formula1=formula, allow_blank=True)
        d.showErrorMessage = True
        d.errorStyle = "stop"
        rs.add_data_validation(d)
        d.add(f"{col}2:{col}501")

    dropdown("G", '"' + ",".join(cfg["profiles"]) + '"')
    dropdown("I", '"' + ",".join(cfg["profiles"]) + '"')
    dropdown("H", '=INDIRECT("Fields_"&$G2)')
    dropdown("J", '=INDIRECT("Fields_"&$I2)')
    dropdown("B", '"YES,NO"')
    dropdown(
        "E",
        '"DATA_COMPLETION,CUSTOMER_SIGNATURE,DOCUMENT_COMPLETION,OFFICER_REVIEW_APPROVAL,DOCUMENT_VERIFICATION,OBSERVATIONS"',
    )
    out = io.BytesIO()
    w.save(out)
    return out.getvalue()


def import_config(data, base):
    errors = []
    cfg = copy.deepcopy(base)

    def fail(sheet, row, column, message):
        errors.append(
            {
                "sheet": sheet,
                "row": row,
                "cell": f"{get_column_letter(column)}{row}",
                "message": message,
            }
        )

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > 20_000_000:
                raise ValueError("Workbook expanded size exceeds 20 MB.")
        w = load_workbook(io.BytesIO(data), data_only=False)
    except Exception:
        return None, [
            {
                "sheet": "Workbook",
                "row": 0,
                "cell": "",
                "message": "Invalid XLSX or expanded size limit exceeded.",
            }
        ]

    def rows(name, headers):
        if name not in w:
            fail(name, 1, 1, "Required sheet missing.")
            return []
        s = w[name]
        if s.max_column > len(headers) and any(
            cell.value is not None
            for row in s.iter_rows(min_col=len(headers) + 1)
            for cell in row
        ):
            fail(name, 1, len(headers) + 1, "Unexpected extra columns.")
            return []
        if s.max_row > 501:
            fail(name, 502, 1, "Maximum 500 entries per sheet.")
            return []
        if [s.cell(1, i + 1).value for i in range(len(headers))] != headers:
            fail(name, 1, 1, "Headers differ from current exported template.")
            return []
        result = []
        for row in s.iter_rows(min_row=2):
            if not any(c.value is not None for c in row):
                continue
            if any(c.data_type == "f" for c in row):
                fail(name, row[0].row, 1, "Formulas are not allowed in configuration.")
                continue
            result.append(
                (row[0].row, {h: row[i].value for i, h in enumerate(headers)})
            )
        return result

    def parse(name, n, r, key, default=None):
        try:
            return json.loads(r[key]) if r.get(key) not in (None, "") else default
        except (ValueError, TypeError):
            fail(name, n, list(r).index(key) + 1, "Invalid JSON.")
            return default

    if 'Document Families' in w.sheetnames:
        family_values={}
        for n,r in rows('Document Families',['family_id','configuration_json']):
            key=r['family_id']
            if not isinstance(key,str) or key in family_values:
                fail('Document Families',n,1,'Family IDs must be distinct strings.')
                continue
            family_values[key]=parse('Document Families',n,r,'configuration_json',{})
        if family_values or 'document_families' in cfg:cfg['document_families']=family_values

    wf = []
    for n, r in rows(
        "Workflow",
        [
            "order",
            "step_id",
            "action",
            "enabled",
            "preset",
            "parameters_json",
            "timeout_seconds",
            "read_poll_retries",
            "on_error",
        ],
    ):
        if r["enabled"] not in {"YES", "NO"}:
            fail("Workflow", n, 4, "Use YES or NO.")
        r["enabled"] = r["enabled"] == "YES"
        r["parameters"] = parse("Workflow", n, r, "parameters_json", {})
        del r["parameters_json"]
        wf.append(r)
    cfg["workflow"] = wf
    for step in wf:
        if step["action"] in {"parse", "extract"}:
            cfg[step["action"] + "_tier"] = step["parameters"].get("tier")
        if step["action"] == "parse":
            cfg["parse_version"] = step["parameters"].get("version")
        if step["action"] == "classify":
            cfg["classification_threshold"] = step["parameters"].get(
                "minimum_confidence"
            )
    general_keys = {
        "report_definitions",
        "document_families",
        "provider",
        "maker_checker",
        "extract_version",
        "report_title",
        "name_directory",
        "customer_aliases",
        "sop_review_bypass",
        "sop_review_bypass_result",
        "sequential_page_extraction",
        "cross_page_reference",
        "grouping_prefixes",
        "suffix_aliases",
        "sop_message_templates",
        "forex_sop_policy",
    }
    general_seen = set()
    for n, r in rows("General Settings", ["key", "value"]):
        key = r["key"]
        if key not in general_keys or key in general_seen:
            fail("General Settings", n, 1, "Unknown or duplicate setting.")
            continue
        general_seen.add(key)
        if key in {"report_definitions", "document_families", "name_directory", "customer_aliases", "suffix_aliases", "sop_message_templates", "forex_sop_policy"}:
            cfg[key] = parse("General Settings", n, r, "value", {})
        elif key == "grouping_prefixes":
            cfg[key] = parse("General Settings", n, r, "value", [])
        elif key in {"maker_checker", "sop_review_bypass", "sequential_page_extraction", "cross_page_reference"}:
            if r["value"] not in {"YES", "NO"}:
                fail("General Settings", n, 2, "Use YES or NO.")
            cfg[key] = r["value"] == "YES"
        elif key == "sop_review_bypass_result":
            if r["value"] not in {"PASS", "REVIEW", "NOT_APPLICABLE"}:
                fail("General Settings", n, 2, "Use PASS, REVIEW, or NOT_APPLICABLE.")
            cfg[key] = r["value"]
        else:
            cfg[key] = r["value"]
    required_general = general_keys - {"report_definitions", "document_families", "customer_aliases", "sop_review_bypass", "sop_review_bypass_result",
                                        "sequential_page_extraction", "cross_page_reference",
                                        "grouping_prefixes", "suffix_aliases", "sop_message_templates", "forex_sop_policy"}
    if general_seen - {"customer_aliases"} != general_keys - {"customer_aliases"}:
        # Old-format workbooks may not have the new keys; only fail if core keys are missing.
        missing_core = required_general - general_seen
        if missing_core:
            fail("General Settings", 1, 1, f"Missing required settings: {', '.join(sorted(missing_core))}.")
    seen = set()
    profile_headers = [
        "document_type",
        "label",
        "suffixes_json",
        "parse_prompt",
        "system_prompt",
        "policy_json",
    ]
    if 'Document Profiles' in w:
        for column in range(7, w['Document Profiles'].max_column + 1):
            header = w['Document Profiles'].cell(1, column).value
            if header in {'system_instruction', 'field_checks_json'} and header not in profile_headers:
                profile_headers.append(header)
    for n, r in rows("Document Profiles", profile_headers):
        name = r["document_type"]
        if name not in cfg["profiles"] or name in seen:
            fail("Document Profiles", n, 1, "Unknown or duplicate document type.")
            continue
        seen.add(name)
        if "system_instruction" in r:
            cfg["profiles"][name]["system_instruction"] = r["system_instruction"]
        if 'field_checks_json' in r and r['field_checks_json'] is not None:
            cfg['profiles'][name]['field_checks'] = parse('Document Profiles', n, r, 'field_checks_json', {})
        cfg["profiles"][name].update(
            label=r["label"],
            suffixes=parse("Document Profiles", n, r, "suffixes_json", []),
            parse_prompt=r["parse_prompt"],
            system_prompt=r["system_prompt"],
            policy=parse("Document Profiles", n, r, "policy_json", {}),
        )
    if seen != set(cfg["profiles"]):
        fail("Document Profiles", 1, 1, "All document profiles must be supplied.")
    cfg["sop_rules"] = []
    for n, r in rows("SOP Rules", RULE_HEADERS):
        if r["enabled"] not in {"YES", "NO"}:
            fail("SOP Rules", n, 2, "Use YES or NO.")
        r["enabled"] = r["enabled"] == "YES"
        r["path"] = (
            str(r.pop("left_document") or "") + "." + str(r.pop("left_field") or "")
        )
        d, f = r.pop("right_document"), r.pop("right_field")
        r["other_path"] = str(d) + "." + str(f) if d and f else ""
        r = {k: ("" if v is None else v) for k, v in r.items()}
        from .sop import validate_business

        try:
            validate_business({**cfg, "sop_rules": [r]})
        except (ValueError, TypeError, KeyError) as exc:
            fail("SOP Rules", n, 1, str(exc))
        cfg["sop_rules"].append(r)
    cfg["templates"] = {}
    for n, r in rows("Case Templates", ["id", "label", "required_json"]):
        if not r["id"] or r["id"] in cfg["templates"]:
            fail("Case Templates", n, 1, "Missing or duplicate template ID.")
            continue
        cfg["templates"][r["id"]] = {
            **copy.deepcopy(
                base["templates"].get(
                    r["id"], {"enabled": True, "description": "", "sop_rule_ids": []}
                )
            ),
            "label": r["label"],
            "required": parse("Case Templates", n, r, "required_json", []),
        }
    if "Transaction Flows" in w:
        seen_flows = set()
        flow_headers = ["id", "description", "enabled_json", "sop_rule_ids_json"]
        if w["Transaction Flows"].max_column > 4:
            flow_headers += [
                "document_family",
                "dataset_id",
                "report_layout",
                "report_context_json",
            ]
        for n, r in rows("Transaction Flows", flow_headers):
            if r["id"] not in cfg["templates"] or r["id"] in seen_flows:
                fail("Transaction Flows", n, 1, "Unknown or duplicate flow ID.")
                continue
            seen_flows.add(r["id"])
            extended = {c.value: i for i, c in enumerate(w["Transaction Flows"][1], 1)}
            flow = cfg["templates"][r["id"]]
            for key in ("document_family", "dataset_id", "report_layout"):
                if key in extended:
                    value = w["Transaction Flows"].cell(n, extended[key]).value
                    if value is not None:
                        flow[key] = value
                    elif key!='dataset_id' or flow.get(key,'absent') is not None:
                        flow.pop(key, None)
            if "report_context_json" in extended:
                try:
                    value = (
                        w["Transaction Flows"]
                        .cell(n, extended["report_context_json"])
                        .value
                    )
                    if value:
                        flow["report_context"] = json.loads(value)
                    else:
                        flow.pop("report_context", None)
                except (ValueError, TypeError):
                    fail(
                        "Transaction Flows",
                        n,
                        extended["report_context_json"],
                        "Invalid JSON.",
                    )
            cfg["templates"][r["id"]].update(
                description=str(r["description"] or ""),
                enabled=parse("Transaction Flows", n, r, "enabled_json", True),
                sop_rule_ids=parse(
                    "Transaction Flows", n, r, "sop_rule_ids_json", None
                ),
            )
    for n, r in rows("Report Context", ["key", "value"]):
        if r["key"] not in base["report_context"]:
            fail("Report Context", n, 1, "Unknown report context key.")
            continue
        cfg["report_context"][r["key"]] = str(r["value"] or "")
    if not errors:
        from .domain import validate_config

        try:
            validate_config(cfg)
        except (ValueError, KeyError, TypeError) as exc:
            fail("Workbook", 1, 1, str(exc))
    return (None if errors else cfg), errors
