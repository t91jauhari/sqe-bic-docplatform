"""Deterministic Forex SOP3 comparisons; never modify extraction or call a model."""
import copy
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

VERSION = 2
from .configuration.native_catalog import native_catalog, legacy_forex_rule

DEFAULT_POLICY = native_catalog()['forex_policy']
CHECKPOINT_LABELS = native_catalog()['forex_checkpoint_labels']
CONTEXT_FIELDS = ("application_document_id", "declaration_document_id", "invoice_document_id", "underlying_document_id", "partial_payment_amount", "partial_payment_currency")


class CheckError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def policy_for(cfg):
    return {**copy.deepcopy(DEFAULT_POLICY), **copy.deepcopy(cfg.get("forex_sop_policy", {})), "version": VERSION}


def validate_policy(cfg):
    policy = cfg.get("forex_sop_policy", {})
    if not isinstance(policy, dict) or set(policy) - set(DEFAULT_POLICY):
        raise ValueError("Unknown Forex SOP policy settings.")
    if "version" in policy and (type(policy["version"]) is not int or policy["version"] != VERSION):
        raise ValueError("Unsupported Forex SOP policy version.")
    for key in ("purpose_codes", "address_aliases"):
        values = policy.get(key, {})
        if not isinstance(values, dict) or len(values) > 2000 or any(not isinstance(k,str) or not k.strip() or not isinstance(v,str) or not v.strip() or max(len(k),len(v)) > 500 for k,v in values.items()):
            raise ValueError(f"Invalid Forex SOP {key} mapping.")
    groups = policy.get("purpose_equivalences", {})
    if not isinstance(groups, dict) or len(groups) > 500:
        raise ValueError("Invalid Forex purpose equivalences.")
    seen = {}
    for key, aliases in groups.items():
        if not isinstance(key,str) or not key.strip() or not isinstance(aliases,list) or not aliases or len(aliases)>100:
            raise ValueError("Purpose groups need a canonical name and aliases.")
        for alias in [key,*aliases]:
            if not isinstance(alias,str) or not alias.strip() or len(alias)>500:
                raise ValueError("Invalid purpose alias.")
            normalized = text(alias)
            if normalized in seen and seen[normalized] != key:
                raise ValueError("A purpose alias cannot belong to two groups.")
            seen[normalized] = key


def scalar(value):
    while isinstance(value, dict):
        if value.get("complete") is False:
            raise CheckError("UNREADABLE_SOURCE", "The source observation is incomplete.")
        key = next((k for k in ("raw", "value", "text", "full_text") if k in value), None)
        if key is None:
            raise CheckError("UNSUPPORTED_VALUE", "A readable scalar observation is required.")
        value = value[key]
    if value is None or isinstance(value, (list,bool)) or isinstance(value,str) and value.strip().casefold() in {"", "missing", "[blank]", "null", "none", "n/a", "not available", "-"}:
        raise CheckError("MISSING_SOURCE_VALUE", "A required source value is missing.")
    if isinstance(value,str) and not any(c.isalnum() for c in value):
        raise CheckError("MISSING_SOURCE_VALUE", "A readable value is required.")
    return value


def text(value):
    return " ".join(unicodedata.normalize("NFC", str(scalar(value))).split()).casefold()


def address(value, policy):
    tokens = re.findall(r"[^\W_]+(?:[-/]\w+)*", text(value), re.UNICODE)
    aliases = {text(k).rstrip("."):text(v) for k,v in policy["address_aliases"].items()}
    tokens = [part for token in tokens for part in aliases.get(token, token).split()]
    # An explicit house-number label is cosmetic; all number/unit tokens remain.
    return tuple(token for i,token in enumerate(tokens) if not (token == "nomor" and i+1<len(tokens) and any(c.isdigit() for c in tokens[i+1])))


def purpose(value, policy, cfg):
    value = text(value)
    codes = {text(k):v for k,v in policy["purpose_codes"].items()}
    master = cfg.get("profiles",{}).get("lld",{}).get("policy",{}).get("purpose_master")
    if isinstance(master,dict): codes = {**{text(k):v for k,v in master.items() if isinstance(v,str)}, **codes}
    value = text(codes[value]) if value in codes else value
    for canonical, aliases in policy["purpose_equivalences"].items():
        if value in {text(canonical), *(text(v) for v in aliases)}:
            return text(canonical)
    return value


def date_value(value, cfg, kind):
    value = str(scalar(value)).strip()
    day_first = cfg.get("profiles",{}).get(kind,{}).get("policy",{}).get("day_first",True)
    formats = ["%Y-%m-%d", "%d-%m-%Y" if day_first else "%m-%d-%Y", "%d/%m/%Y" if day_first else "%m/%d/%Y"]
    for fmt in formats:
        try: return datetime.strptime(re.sub(r"\s*([- /])\s*",r"\1",value),fmt).date()
        except ValueError: pass
    raise CheckError("INVALID_DATE", "Date is missing, ambiguous or unsupported by the document date policy.")


def currency_value(value):
    import pycountry
    value = str(scalar(value)).strip().upper()
    if len(value)!=3 or not pycountry.currencies.get(alpha_3=value):
        raise CheckError("INVALID_CURRENCY", "An explicit recognized three-letter currency is required.")
    return value


def money(value, currency, locale=None):
    source = scalar(value)
    if isinstance(source, (int, float, Decimal)):
        try: result = Decimal(str(source))
        except InvalidOperation: raise CheckError("INVALID_AMOUNT", "Invalid numeric amount.")
        if not result.is_finite() or result <= 0: raise CheckError("INVALID_AMOUNT", "Monetary amount must be positive and finite.")
        return result
    value = str(source).strip().replace("\u00a0", " ")
    found = re.match(r"^([A-Za-z]{3})\s+", value)
    if found:
        if currency_value(found[1]) != currency: raise CheckError("CURRENCY_MISMATCH", "Currency embedded in the amount contradicts its currency field.")
        value = value[found.end():]
    value = re.sub(r"\s*([.,])\s*", r"\1", value)
    if re.search(r"\s", value):
        if not re.fullmatch(r"\d{1,3}(?: \d{3})+(?:[.,]\d+)?", value):
            raise CheckError("INVALID_AMOUNT", "Malformed space-grouped amount.")
        value = value.replace(" ", "")
    if not re.fullmatch(r"\d[\d.,]*",value): raise CheckError("INVALID_AMOUNT", "Amount must contain only a positive monetary value.")
    if "." in value and "," in value:
        dec = "." if value.rfind(".") > value.rfind(",") else ","
        group = "," if dec == "." else "."
        if not re.fullmatch(r"\d{1,3}(?:"+re.escape(group)+r"\d{3})+"+re.escape(dec)+r"\d+",value):
            raise CheckError("INVALID_AMOUNT", "Malformed grouped amount.")
        value = value.replace(group, "").replace(dec,".")
    elif "." in value or "," in value:
        sep = "." if "." in value else ","
        if value.count(sep)>1:
            if not re.fullmatch(r"\d{1,3}(?:"+re.escape(sep)+r"\d{3})+",value): raise CheckError("INVALID_AMOUNT", "Malformed thousands grouping.")
            value = value.replace(sep, "")
        else:
            a,b = value.split(sep)
            if not a or not b: raise CheckError("INVALID_AMOUNT", "Amount has an incomplete decimal separator.")
            if len(b)==3 and len(a)<=3:
                grouping = "." if locale == "id_ID" else "," if locale in {"en_US","en_GB"} else None
                decimal = "," if locale == "id_ID" else "." if locale in {"en_US","en_GB"} else None
                if sep == grouping: value = a+b
                elif sep != decimal: raise CheckError("AMBIGUOUS_AMOUNT", "Three-digit separator needs an explicit number locale.")
                else: value = a+"."+b
            else: value = value.replace(sep,".")
    try: result = Decimal(value)
    except InvalidOperation: raise CheckError("INVALID_AMOUNT", "Invalid decimal amount.")
    if not result.is_finite() or result <= 0: raise CheckError("INVALID_AMOUNT", "Monetary amount must be positive and finite.")
    return result


def number_locale(cfg, kind, field):
    policy = cfg.get("profiles",{}).get(kind,{}).get("policy",{})
    return policy.get("field_number_locales",{}).get(field,policy.get("number_locale"))


def select_document(documents, kind, context):
    matches = [d for d in documents if d["doc_type"] == kind and d["status"] == "COMPLETED"]
    key = {"application":"application_document_id", "invoice":"invoice_document_id"}.get(kind)
    chosen = context.get(key) if key else None
    if kind.startswith("valas_declaration"):
        chosen = context.get("declaration_document_id")
    if chosen:
        matches = [d for d in matches if d["id"] == chosen]
    if len(matches)!=1:
        raise CheckError("AMBIGUOUS_DOCUMENT" if len(matches)>1 else "MISSING_REQUIRED_DOCUMENT", f"Select one completed {kind} document; found {len(matches)}.")
    return matches[0]


def effective_rule(rule):
    return legacy_forex_rule(rule)


def evaluate_rule(rule, documents, cfg, context):
    r = effective_rule(rule)
    policy = policy_for(cfg)
    number = int(r["source_ref"].split(":")[1])
    finding = {"rule_id":r["id"], "field":r["path"], "source_ref":r["source_ref"], "scope_basis":r["scope_basis"], "category":r["report_category"], "eligible":True, "result":"FAIL", "actual":None, "expected":None, "message":r.get("label",r["id"]), "evidence":{"document_ids":[],"reference_document_ids":[],"path":r["path"],"other_path":r.get("other_path"),"policy":r.get("comparison_policy"),"evaluator_version":VERSION,"comparisons":[]}}
    evidence = finding["evidence"]
    refs = []
    def get(path, side="left"):
        kind,*parts = path.split(".")
        doc = select_document(documents,kind,context)
        bucket = "document_ids" if side == "left" else "reference_document_ids"
        if doc["id"] not in evidence[bucket]: evidence[bucket].append(doc["id"])
        refs.append((doc,parts[0] if parts else ""))
        value = doc["normalized"]
        for part in parts: value = value.get(part) if isinstance(value,dict) else None
        return value,doc
    def compare(a,b,method):
        evidence["comparisons"].append({"method":method,"actual":str(a),"expected":str(b),"match":a==b})
        if a != b: raise CheckError("VALUE_MISMATCH", f"The {method} comparison differs.")
    def amount(path, currency_path, side):
        value,doc = get(path,side)
        currency,_ = get(currency_path,side)
        code = currency_value(currency)
        locale = number_locale(cfg,doc["doc_type"],path.split(".")[1])
        return money(value,code,locale),code,value
    def invoice_payment_basis():
        basis = context.get("payment_basis", "UNKNOWN")
        evidence["payment_basis"] = basis
        full_path, full_currency = "invoice.final_total_amount.amount", "invoice.final_total_amount.currency"
        if basis == "FULL_INVOICE":
            return amount(full_path,full_currency,"right")
        if basis == "PROGRESS_CLAIM":
            return amount("invoice.claim_note.amount","invoice.claim_note.currency","right")
        if basis == "PARTIAL_PAYMENT":
            if not context.get("annotation",{}).get("evidence"):
                raise CheckError("PAYMENT_EVIDENCE_REQUIRED", "Partial payment needs a document-supported context annotation.")
            code = currency_value(context.get("partial_payment_currency"))
            expected = money(context.get("partial_payment_amount"),code)
            full,full_code,_ = amount(full_path,full_currency,"right")
            compare(code,full_code,"partial-payment invoice currency")
            if expected > full:
                raise CheckError("INVALID_PAYMENT_BASIS", "Partial payment exceeds the supported invoice total.")
            return expected,code,context.get("partial_payment_amount")
        raise CheckError("MISSING_PAYMENT_BASIS", "Choose full invoice, documented progress claim or documented partial payment.")
    def invoice_parties(invoice):
        values = invoice["normalized"]
        scalar(values.get("invoice_number"))
        sender,_ = get("application.remitter.name")
        recipient,_ = get("lld.beneficiary_name","right")
        refs.append((invoice,"to_name"))
        buyer = values.get("to_name")
        seller = values.get("beneficiary_name")
        try: scalar(seller)
        except CheckError as exc:
            if exc.code != "MISSING_SOURCE_VALUE": raise
            seller = values.get("from_name")
            refs.append((invoice,"from_name"))
        else:
            refs.append((invoice,"beneficiary_name"))
        compare(text(buyer),text(sender),"invoice buyer / sender name")
        compare(text(seller),text(recipient),"invoice payee / LLD beneficiary name")
        evidence["invoice_number"] = str(scalar(values.get("invoice_number")))
    try:
        completed = [d for d in documents if d["status"] == "COMPLETED"]
        declarations = [d for d in completed if d["doc_type"].startswith("valas_declaration")]
        selected_declaration = context.get("declaration_document_id")
        if selected_declaration: declarations = [d for d in declarations if d["id"] == selected_declaration]
        if len(declarations)>1 and context.get("threshold_state") in {"ABOVE","WITHIN"}:
            kind = "valas_declaration_1" if context["threshold_state"] == "ABOVE" else "valas_declaration_2"
            declarations = [d for d in declarations if d["doc_type"]==kind]
        valas2 = len(declarations)==1 and declarations[0]["doc_type"]=="valas_declaration_2"
        if number in {2,9,10,12} and valas2:
            if context.get("threshold_state") == "ABOVE": raise CheckError("MISSING_REQUIRED_DOCUMENT", "Above-threshold context requires Valas 1; Valas 2 cannot substitute for its missing fields.")
            finding.update(result="NOT_APPLICABLE",eligible=False,reason_code="DECLARATION_VARIANT_NOT_APPLICABLE")
            finding["message"] += " Valas 2 is the applicable uploaded declaration; this Valas 1-only field is not on that form."
            return finding
        cond = r.get("condition_operator","always")
        if cond in {"equals","in"}:
            observed = context.get(r.get("condition_key"),"UNKNOWN")
            if observed in {None,"","UNKNOWN"}: raise CheckError("MISSING_CASE_CONTEXT", f"Set {r.get('condition_key')} from document-supported evidence.")
            choices = str(r.get("condition_value","")).split(",") if cond == "in" else [r.get("condition_value")]
            if observed not in choices:
                finding.update(result="NOT_APPLICABLE",eligible=False,reason_code="EXPLICITLY_NOT_APPLICABLE")
                return finding
        elif cond == "document_present" and not any(d["doc_type"]==r.get("condition_value") for d in completed):
            finding.update(result="NOT_APPLICABLE",eligible=False,reason_code="EXPLICITLY_NOT_APPLICABLE")
            return finding
        if number in {2,6,9,10,12} and len(declarations)>1:
            raise CheckError("AMBIGUOUS_DOCUMENT", "Choose the applicable Valas declaration before comparison.")
        if number == 6 and valas2:
            r["other_path"] = "valas_declaration_2.customer_name"
            evidence["other_path"] = r["other_path"]
        actual,left = get(r["path"])
        expected,right = get(r.get("other_path") or r["path"],"right")
        finding.update(actual=actual,expected=expected)
        op = r["operator"]
        if op == "signature_visual_consistency":
            finding.update(result="REVIEW",reason_code="VISUAL_REVIEW_REQUIRED")
            return finding
        if op == "invoice_linkage":
            invoice_parties(left)
            lld_amount,lld_currency,_ = amount("lld.transaction_value.amount","lld.transaction_value.currency","right")
            invoice_amount,invoice_currency,_ = invoice_payment_basis()
            compare(lld_currency,invoice_currency,"linked invoice / LLD currency")
            compare(lld_amount,invoice_amount,"linked invoice / LLD payment amount")
            evidence["linkage_method"] = "invoice identity and corresponding party roles"
            underlying_id = context.get("underlying_document_id")
            if underlying_id:
                candidates = [d for d in completed if d["id"]==underlying_id and d["doc_type"]=="invoice" and d["id"]!=left["id"]]
                if len(candidates)!=1: raise CheckError("INVALID_DOCUMENT_SELECTION", "Choose a distinct completed supporting invoice document.")
                underlying = candidates[0]
                evidence["reference_document_ids"].append(underlying["id"])
                refs.extend([(underlying,"invoice_number"),(underlying,"final_total_amount"),(left,"final_total_amount")])
                compare(str(scalar(actual)).strip(),str(scalar(underlying["normalized"].get("invoice_number"))).strip(),"underlying invoice reference")
                for field in ("final_total_amount",):
                    a=left["normalized"].get(field) or {};b=underlying["normalized"].get(field) or {}
                    if not isinstance(a,dict) or not isinstance(b,dict): raise CheckError("INVALID_AMOUNT", "Supporting invoice totals need amount and currency fields.")
                    ca,cb=currency_value(a.get("currency")),currency_value(b.get("currency"))
                    compare(ca,cb,"underlying invoice currency")
                    compare(money(a.get("amount"),ca,number_locale(cfg,"invoice","final_total_amount")),money(b.get("amount"),cb,number_locale(cfg,"invoice","final_total_amount")),"underlying invoice total")
            details = right["normalized"].get("details")
            if details:
                reference = str(scalar(actual)).strip()
                evidence["invoice_reference_visible_in_lld_details"] = bool(re.search(r"(?<!\w)"+re.escape(reference)+r"(?!\w)",str(scalar(details)),re.I))
        elif op in {"match_exact","match_address","match_purpose"}:
            if r.get("comparison_policy") == "identifier_exact":
                if not isinstance(scalar(actual),str) or not isinstance(scalar(expected),str): raise CheckError("INVALID_IDENTIFIER", "NIK must be stored as text to preserve all digits.")
                a,b = str(scalar(actual)).strip(),str(scalar(expected)).strip()
                if not re.fullmatch(r"\d{16}",a) or not re.fullmatch(r"\d{16}",b): raise CheckError("INVALID_IDENTIFIER", "NIK must contain exactly 16 digits, preserving leading zeros.")
            elif op == "match_address": a,b=address(actual,policy),address(expected,policy)
            elif op == "match_purpose":
                a,b=purpose(actual,policy,cfg),purpose(expected,policy,cfg)
                if a!=b and (str(a).isdigit() or str(b).isdigit()): raise CheckError("UNMAPPED_PURPOSE", "Configure an approved purpose-code/description mapping; equivalence is not inferred.")
            else: a,b=text(actual),text(expected)
            compare(a,b,op)
            if number == 6: evidence["party_roles"] = "Valas customer = sender; recipient is independently verified by checkpoints 7 and 14, never equated with the sender."
        elif op in {"date_equal","date_on_or_after"}:
            a,b=date_value(actual,cfg,left["doc_type"]),date_value(expected,cfg,right["doc_type"])
            if op == "date_equal": compare(a,b,"calendar date")
            elif a < b: raise CheckError("VALUE_MISMATCH", "Document date is before its reference date.")
        elif op == "match_money":
            a,ca,_=amount(r["path"],r["currency_path"],"left")
            if r.get("comparison_policy") == "invoice_payment_basis":
                b,cb,expected = invoice_payment_basis()
            else:
                b,cb,expected = amount(r["other_path"],r["other_currency_path"],"right")
            finding["expected"] = expected
            compare(ca,cb,"currency")
            compare(a,b,"exact monetary amount")
        else: raise CheckError("UNSUPPORTED_POLICY", "This Forex checkpoint needs a registered executable comparison operator.")
        for doc,root in refs:
            if root in doc.get("overrides",{}): continue
            issues=doc.get("validation",{}).get("fields",{}).get(root,{}).get("issues",[])
            if any(i.get("code") in {"LOW_EXTRACTION_CONFIDENCE","MISSING_CONFIDENCE","UNREADABLE_TEXT","INCOMPLETE_TEXT","CROP_EVIDENCE_REQUIRED","CROP_LINK_REVIEW_REQUIRED"} for i in issues):
                raise CheckError("UNVERIFIED_SOURCE", "Comparison source has unresolved readability or extraction-quality issues.")
        finding.update(result="PASS",reason_code="CHECK_PASSED")
    except CheckError as exc:
        finding.update(result="FAIL",reason_code=exc.code)
        finding["message"] += " " + str(exc)
    return finding


def package_summary(findings):
    from .sop_scoring import point_summary
    atomic=[f for f in findings if f.get("source_ref","").startswith("SOP3:")]
    if not atomic: return {}
    checkpoints=[]
    for number in range(1,16):
        children=[f for f in atomic if f["source_ref"]==f"SOP3:{number}"]
        applicable=[f for f in children if f["result"]!="NOT_APPLICABLE"]
        expected_children = 3 if number == 2 else 2 if number == 7 else 1
        required_fields = {2:{"ektp.nik","ektp.name","ektp.address"},7:{"application.beneficiary.name","application.beneficiary.address"}}.get(number)
        missing_children = len(required_fields-{f.get("field") for f in children}) if required_fields else max(0, expected_children-len(children))
        result="FAIL" if any(f["result"]=="FAIL" for f in applicable) or missing_children else "REVIEW" if any(f["result"]=="REVIEW" for f in applicable) else "PASS" if applicable else "NOT_APPLICABLE"
        checkpoints.append({"rule_id":f"SOP3:{number}","label":CHECKPOINT_LABELS[number-1],"result":result,"eligible":result!="NOT_APPLICABLE","missing_field_checks":missing_children,"child_rules":[f["rule_id"] for f in children]})
    return {"forex":{"version":VERSION,"summary":point_summary(checkpoints),"atomic_summary":point_summary(atomic),"checkpoints":checkpoints,"coverage":{"present":len({f["source_ref"] for f in atomic}),"expected":15,"missing_field_checks":sum(c["missing_field_checks"] for c in checkpoints),"complete":len({f["source_ref"] for f in atomic})==15 and not any(c["missing_field_checks"] for c in checkpoints)},"scoring_unit":"source checkpoint; all applicable child checks must pass; missing checkpoints fail"}}
