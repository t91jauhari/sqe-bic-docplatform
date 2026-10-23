"""Cryptographic utilities independent of authentication transport."""

import base64
import hashlib
import hmac
import os
from cryptography.fernet import Fernet
from .settings import settings


def hash_password(password):
    salt = os.urandom(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return base64.b64encode(salt + result).decode()


def verify_password(password, stored):
    try:
        data = base64.b64decode(stored)
        return hmac.compare_digest(
            data[16:],
            hashlib.scrypt(
                password.encode(), salt=data[:16], n=16384, r=8, p=1, dklen=32
            ),
        )
    except (ValueError, TypeError):
        return False


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def encrypt(value):
    return (
        Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(settings.secret.encode()).digest())
        )
        .encrypt(value.encode())
        .decode()
    )


def decrypt(value):
    return (
        Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(settings.secret.encode()).digest())
        )
        .decrypt(value.encode())
        .decode()
        if value
        else ""
    )
