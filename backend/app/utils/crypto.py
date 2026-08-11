from cryptography.fernet import Fernet
from ..config import settings
import base64
import hashlib


def get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if len(key) < 32:
        key = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
    else:
        key = base64.urlsafe_b64encode(key.encode()[:32])
    return Fernet(key)


def encrypt_field(value: str) -> str:
    if not value:
        return ""
    return get_fernet().encrypt(value.encode()).decode()


def decrypt_field(value: str) -> str:
    if not value:
        return ""
    return get_fernet().decrypt(value.encode()).decode()