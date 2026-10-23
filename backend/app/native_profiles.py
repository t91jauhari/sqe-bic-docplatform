"""Native engine registry and captured compatibility defaults."""

import sys
from .settings import ROOT
from .configuration.native_catalog import native_catalog

ENGINE = ROOT / "engine"
sys.path.insert(0, str(ENGINE))
from context import check_directory
from profiles import PROFILE_NAMES, get_profile
from account_opening.profiles import REFERENCE as ACCOUNT_REFERENCE

_NATIVE_CATALOG = native_catalog()
LABELS = _NATIVE_CATALOG["labels"]
CLASSIFY_DESCRIPTIONS = _NATIVE_CATALOG["classification_descriptions"]
SUFFIXES = _NATIVE_CATALOG["suffixes"]
GROUPING_PREFIXES = _NATIVE_CATALOG["grouping_prefixes"]
SUFFIX_ALIASES = _NATIVE_CATALOG["suffix_aliases"]
SOP_MESSAGE_TEMPLATES = _NATIVE_CATALOG["message_templates"]
