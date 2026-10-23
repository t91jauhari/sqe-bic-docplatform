"""Shared authorization policies and request-independent API infrastructure."""
import logging
import secrets
from app.security import hash_password, require_roles

WRITE = require_roles("bank_admin", "branch_admin", "officer", "reviewer")
REVIEW = require_roles("bank_admin", "branch_admin", "reviewer")
ADMIN = require_roles("bank_admin")
USER_ADMIN = require_roles("bank_admin", "branch_admin")
log = logging.getLogger("sqe.api")
DUMMY_PASSWORD = hash_password(secrets.token_urlsafe(24))
