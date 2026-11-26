from temporalio import activity
from temporalio.exceptions import ApplicationError

from common import mock_agents, storage
from common.models import BatchSimResult, SimulationResult


def _sim_prefix(dataset: str, golden_version: str, run_id: str) -> str:
    return f"sim/{dataset}/{golden_version}/{run_id}"


@activity.defn
async def load_manifest(dataset: str, golden_version: str) -> list:
    """Return the batch ids of a *specific golden-set version* (只帶版本參照，不帶資料)."""
    key = f"golden/{dataset}/{golden_version}/manifest.json"
    if not storage.exists(key):
        # 重試也不會變出 golden set => non-retryable，立刻失敗讓人看到
        raise ApplicationError(f"golden set not ready: {key}", non_retryable=True)
    return storage.get_json(key)["batches"]


@activity.defn
async def simulate_batch(
    dataset: str, golden_version: str, batch_id: str, agent_variant: str, run_id: str
) -> BatchSimResult:
    """Run the mock agent over one golden batch. Idempotent per (run_id, batch_id)."""
    router = mock_agents.VARIANTS.get(agent_variant)
    if router is None:
        raise ApplicationError(f"unknown agent_variant: {agent_variant}", non_retryable=True)

    out_key = f"{_sim_prefix(dataset, golden_version, run_id)}/{batch_id}.json"
    if storage.exists(out_key):
        done = storage.get_json(out_key)
        return BatchSimResult(batch_id, done["total"], done["passed"])

    cases = storage.get_json(f"golden/{dataset}/{golden_version}/cases/{batch_id}.json")["cases"]
    rows = []
    for case in cases:
        got = router(case["question"])  # 正式專案：mock agent + mock tools（無副作用）
        rows.append(
            {
                "id": case["id"],
                "expected": case["expected_agents"],
                "got": got,
                "pass": sorted(got) == sorted(case["expected_agents"]),
            }
        )
    passed = sum(1 for r in rows if r["pass"])
    storage.put_json(out_key, {"batch_id": batch_id, "total": len(rows), "passed": passed, "cases": rows})
    return BatchSimResult(batch_id, len(rows), passed)


@activity.defn
async def finalize_report(
    dataset: str, golden_version: str, agent_variant: str, run_id: str, results: list
) -> SimulationResult:
    total = sum(r.total for r in results)
    passed = sum(r.passed for r in results)
    rate = round(passed / total, 4) if total else 0.0
    report_key = f"{_sim_prefix(dataset, golden_version, run_id)}/report.json"
    storage.put_json(
        report_key,
        {
            "run_id": run_id,
            "dataset": dataset,
            "golden_version": golden_version,
            "agent_variant": agent_variant,
            "total": total,
            "passed": passed,
            "pass_rate": rate,
        },
    )
    return SimulationResult(
        run_id=run_id,
        dataset=dataset,
        golden_version=golden_version,
        agent_variant=agent_variant,
        total=total,
        passed=passed,
        pass_rate=rate,
        report_key=report_key,
    )
