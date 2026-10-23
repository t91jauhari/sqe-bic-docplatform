"""Compatibility facade; implementations live in their owning feature modules."""

from .native_profiles import (
    ACCOUNT_REFERENCE,
    CLASSIFY_DESCRIPTIONS,
    ENGINE,
    GROUPING_PREFIXES,
    LABELS,
    PROFILE_NAMES,
    SOP_MESSAGE_TEMPLATES,
    SUFFIXES,
    SUFFIX_ALIASES,
    check_directory,
    get_profile,
)
from .auditing import serial, audit
from .configuration.bootstrap import default_config, seed, upgrade_profiles
from .configuration.validation import validate_config
from .configuration.revisions import latest_config
from .filename_routing import route
from .legacy_case_rules import riplay_identity_findings, extract_path, evaluate_rules
from .case_lifecycle import enqueue, refresh_case
