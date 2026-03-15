import base64
import hashlib
import hmac
import json
import os
import secrets
import time


AUTH_SECRET = os.getenv("AUTH_SECRET", "cusine-aml-dev-secret")
TOKEN_TTL_SECONDS = 60 * 60 * 12


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False

    salt, expected = stored_hash.split("$", 1)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(payload: dict) -> str:
    body = {**payload, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    encoded_body = base64.urlsafe_b64encode(json.dumps(body).encode("utf-8")).decode("utf-8")
    signature = hmac.new(AUTH_SECRET.encode("utf-8"), encoded_body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded_body}.{signature}"


def decode_access_token(token: str) -> dict | None:
    try:
        encoded_body, signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(
        AUTH_SECRET.encode("utf-8"), encoded_body.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded_body.encode("utf-8")).decode("utf-8"))
    except Exception:
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None

    return payload