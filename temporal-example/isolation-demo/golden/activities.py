import hashlib
import re
from pathlib import Path

from temporalio import activity

from common import storage
from common.models import CleanBatchResult, ManifestInfo

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TW_MOBILE = re.compile(r"\b09\d{2}-?\d{3}-?\d{3}\b")


def redact(text: str) -> str:
    return _TW_MOBILE.sub("<PHONE>", _EMAIL.sub("<EMAIL>", text))


def _cases_key(dataset: str, version: str, batch_id: str) -> str:
    # 輸出路徑完全由輸入決定 => activity 冪等：重跑同一批 = 寫到同一個位置
    return f"golden/{dataset}/{version}/cases/{batch_id}.json"


@activity.defn
async def list_log_batches(dataset: str, offset: int, limit: int) -> list:
    """Return up to `limit` raw-log batch ids starting at `offset` (sorted, stable).

    只回傳 id，不回傳內容。正式環境要在整個流程開始時固定一個 snapshot / 截止時間，
    避免 offset 分頁期間又有新檔案進來。
    """
    ids = [Path(k).stem for k in storage.list_keys(f"raw/{dataset}", suffix=".jsonl")]
    return ids[offset : offset + limit]


@activity.defn
async def clean_batch(dataset: str, version: str, batch_id: str, force: bool) -> CleanBatchResult:
    """Clean one raw-log batch -> golden cases. Idempotent and heartbeating."""
    out_key = _cases_key(dataset, version, batch_id)
    if not force and storage.exists(out_key):
        existing = storage.get_json(out_key)
        return CleanBatchResult(batch_id, read=0, kept=len(existing["cases"]), skipped_existing=True)

    seen = set()
    cases = []
    read = 0
    for i, row in enumerate(storage.read_jsonl(f"raw/{dataset}/{batch_id}.jsonl")):
        read += 1
        if i % 50 == 0:
            # 長批次一定要 heartbeat：worker 掛掉時 Temporal 才能很快（heartbeat timeout）重派，
            # 而不是等到整個 start_to_close_timeout。
            activity.heartbeat(i)

        question = (row.get("question") or "").strip()
        if not question or row.get("feedback") != "good":
            continue  # 只留使用者給「好評」的對話當 golden
        question = redact(question)
        norm = " ".join(question.lower().split())
        if norm in seen:
            continue  # batch 內去重（跨 batch 去重留給後續步驟，這裡刻意簡化）
        seen.add(norm)
        cases.append(
            {
                "id": hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12],  # 穩定 id
                "question": question,
                "expected_agents": row.get("agents") or ["general"],
            }
        )

    storage.put_json(out_key, {"batch_id": batch_id, "dataset": dataset, "version": version, "cases": cases})
    return CleanBatchResult(batch_id, read=read, kept=len(cases), skipped_existing=False)


@activity.defn
async def write_manifest(dataset: str, version: str) -> ManifestInfo:
    """Write the golden-set manifest that (3) simulation consumes by version."""
    keys = storage.list_keys(f"golden/{dataset}/{version}/cases", suffix=".json")
    batches = [Path(k).stem for k in keys]
    total = sum(len(storage.get_json(k)["cases"]) for k in keys)
    manifest_key = f"golden/{dataset}/{version}/manifest.json"
    storage.put_json(
        manifest_key,
        {"dataset": dataset, "version": version, "batches": batches, "cases": total},
    )
    return ManifestInfo(manifest_key=manifest_key, batches=len(batches), cases=total)
