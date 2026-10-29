"""client_secret 的 hash / 驗證，直接用 bcrypt，避免拉 passlib 整套相依。"""
import bcrypt


def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def verify_secret(secret: str, secret_hash: str) -> bool:
    return bcrypt.checkpw(secret.encode(), secret_hash.encode())
