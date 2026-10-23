"""Document-specific schema/prompt/policy routing without changing application defaults."""

from importlib import import_module

from account_opening.profiles import NAMES as ACCOUNT_PROFILE_NAMES

PROFILE_NAMES = (
    "application",
    "lld",
    "invoice",
    "valas_declaration_2",
    "valas_declaration_1",
    "ektp",
    "riplay",
) + ACCOUNT_PROFILE_NAMES


def get_profile(name):
    if name in ACCOUNT_PROFILE_NAMES:
        from account_opening.profiles import get

        return get(name)
    if name == "application":
        schema = import_module("schema")
        validator = import_module("validation").validate
        return {
            "name": name,
            "schema": schema.SCHEMA,
            "columns": schema.COLUMNS,
            "parse_prompt": schema.PARSE_PROMPT,
            "system_prompt": schema.SYSTEM_PROMPT,
            "policy": "policy.json",
            "sample": "samples/customer_transaction.pdf",
            "validate": validator,
        }
    if name == "lld":
        schema = import_module("lld.schema")
        validator = import_module("lld.validation").validate
        return {
            "name": name,
            "schema": schema.SCHEMA,
            "columns": schema.COLUMNS,
            "parse_prompt": schema.PARSE_PROMPT,
            "system_prompt": schema.SYSTEM_PROMPT,
            "policy": "lld/policy.json",
            "sample": "samples/customer_lld.pdf",
            "validate": validator,
        }
    if name == "invoice":
        schema = import_module("invoice.schema")
        validator = import_module("invoice.validation").validate
        return {
            "name": name,
            "schema": schema.SCHEMA,
            "columns": schema.COLUMNS,
            "parse_prompt": schema.PARSE_PROMPT,
            "system_prompt": schema.SYSTEM_PROMPT,
            "policy": "invoice/policy.json",
            "sample": "samples/customer_invoice.pdf",
            "validate": validator,
        }
    if name == "valas_declaration_2":
        schema = import_module("valas2.schema")
        validator = import_module("valas2.validation").validate
        return {
            "name": name,
            "schema": schema.SCHEMA,
            "columns": schema.COLUMNS,
            "parse_prompt": schema.PARSE_PROMPT,
            "system_prompt": schema.SYSTEM_PROMPT,
            "policy": "valas2/policy.json",
            "sample": "samples/customer_valas2.pdf",
            "validate": validator,
        }
    if name == "valas_declaration_1":
        schema = import_module("valas1.schema")
        validator = import_module("valas1.validation").validate
        return {
            "name": name,
            "schema": schema.SCHEMA,
            "columns": schema.COLUMNS,
            "parse_prompt": schema.PARSE_PROMPT,
            "system_prompt": schema.SYSTEM_PROMPT,
            "policy": "valas1/policy.json",
            "sample": "samples/customer_valas1.pdf",
            "validate": validator,
        }
    if name == "ektp":
        schema = import_module("ektp.schema")
        validator = import_module("ektp.validation").validate
        return {
            "name": name,
            "schema": schema.SCHEMA,
            "columns": schema.COLUMNS,
            "parse_prompt": schema.PARSE_PROMPT,
            "system_prompt": schema.SYSTEM_PROMPT,
            "policy": "ektp/policy.json",
            "sample": "samples/customer_ektp.pdf",
            "validate": validator,
        }
    if name == "riplay":
        schema = import_module("riplay.schema")
        validator = import_module("riplay.validation").validate
        return {
            "name": name,
            "schema": schema.SCHEMA,
            "columns": schema.COLUMNS,
            "parse_prompt": schema.PARSE_PROMPT,
            "system_prompt": schema.SYSTEM_PROMPT,
            "policy": "riplay/policy.json",
            "sample": "samples/customer_riplay.pdf",
            "validate": validator,
        }
    raise ValueError(f"Unknown document profile: {name}")
