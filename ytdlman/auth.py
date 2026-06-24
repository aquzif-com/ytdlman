import hashlib
import secrets


def hash_password(password: str, salt: bytes, iterations: int) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return dk.hex()


def is_configured(auth_cfg) -> bool:
    return bool(auth_cfg.username and auth_cfg.password_hash and auth_cfg.salt)


def verify_password(password: str, auth_cfg) -> bool:
    if not is_configured(auth_cfg):
        return False
    candidate = hash_password(password, bytes.fromhex(auth_cfg.salt), auth_cfg.iterations)
    return secrets.compare_digest(candidate, auth_cfg.password_hash)


def create_account(config, username: str, password: str, *, save) -> None:
    salt = secrets.token_bytes(16)
    config.auth.username = username
    config.auth.salt = salt.hex()
    config.auth.password_hash = hash_password(password, salt, config.auth.iterations)
    if not config.auth.secret_key:
        config.auth.secret_key = secrets.token_hex(32)
    save()
