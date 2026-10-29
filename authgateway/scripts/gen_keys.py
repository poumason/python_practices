"""產生 AuthGateway 自己簽發 system token 用的 RSA keypair（demo 用）。

用法：
    python scripts/gen_keys.py
"""
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_DIR = Path(__file__).parent.parent / "keys"


def main() -> None:
    KEY_DIR.mkdir(exist_ok=True)
    private_path = KEY_DIR / "private.pem"
    public_path = KEY_DIR / "public.pem"

    if private_path.exists() or public_path.exists():
        print(f"金鑰已存在於 {KEY_DIR}，跳過產生。若要重新產生請先手動刪除。")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    print(f"已產生金鑰: {private_path}, {public_path}")


if __name__ == "__main__":
    main()
