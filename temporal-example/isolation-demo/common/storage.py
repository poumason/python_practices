"""A tiny local-disk stand-in for object storage (MinIO / S3).

重點：workflow 與 activity 之間只傳 *key*（參照），不傳資料本身，
所以 Temporal 的 payload（約 2MB）與 Event History 大小限制不會被踩到。
寫入是 atomic（暫存檔 + rename），re-run 時不會讀到寫一半的檔案。
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Iterator

from common import settings


def _root() -> Path:
    return Path(settings.DATA_DIR).resolve()


def _path(key: str) -> Path:
    root = _root()
    path = (root / key).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"key escapes data dir: {key}")
    return path


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def exists(key: str) -> bool:
    return _path(key).exists()


def put_json(key: str, obj) -> None:
    _atomic_write(_path(key), json.dumps(obj, ensure_ascii=False, indent=2))


def get_json(key: str):
    return json.loads(_path(key).read_text(encoding="utf-8"))


def write_jsonl(key: str, rows) -> None:
    _atomic_write(_path(key), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def read_jsonl(key: str) -> Iterator[dict]:
    with _path(key).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def list_keys(prefix: str, suffix: str = "") -> list:
    """Sorted keys under `prefix` (sorted => stable order across activity retries)."""
    base = _path(prefix)
    if not base.is_dir():
        return []
    root = _root()
    return sorted(
        p.relative_to(root).as_posix()
        for p in base.rglob("*")
        if p.is_file() and p.name.endswith(suffix) and not p.name.endswith(".tmp")
    )
