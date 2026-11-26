"""Workflow-level tests using Temporal's time-skipping test server.

首次執行 WorkflowEnvironment.start_time_skipping() 會自動下載測試用 server binary，需要網路。
"""
import asyncio
import uuid

from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment

import seed_data
import worker as worker_module
from chat.workflows import ChatOrchestrationWorkflow
from common import mock_agents, storage
from common.models import ChatRequest, GoldenSetRequest, SimulationRequest
from common.names import CHAT_QUEUE, GOLDEN_QUEUE, SIM_QUEUE
from golden import workflows as golden_workflows
from golden.activities import redact
from golden.workflows import GoldenSetWorkflow
from simulation.workflows import SimulationWorkflow


def _run(coro):
    return asyncio.run(coro)


async def _with_env(scenario):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        return await scenario(env.client)


async def _golden(client: Client, dataset="demo", version="v1", wid=None, force=False):
    return await client.execute_workflow(
        GoldenSetWorkflow.run,
        GoldenSetRequest(dataset=dataset, version=version, force=force),
        id=wid or f"golden-{dataset}-{version}",
        task_queue=GOLDEN_QUEUE,
    )


# ---------------------------------------------------------------- unit-ish
def test_redact_removes_email_and_phone():
    assert redact("mail a@b.com call 0912-345-678") == "mail <EMAIL> call <PHONE>"


def test_router_is_deterministic_and_flaky_variant_misroutes_some():
    qs = [f"refund invoice {i}" for i in range(30)]
    assert all(mock_agents.route(q) == ["billing"] for q in qs)
    assert mock_agents.flaky_route(qs[0]) == mock_agents.flaky_route(qs[0])
    assert any(mock_agents.flaky_route(q) != ["billing"] for q in qs)


# ---------------------------------------------------------------- (1) chat
def test_chat_routes_to_multiple_domain_agents():
    async def scenario(client):
        async with worker_module.build_worker(client, "chat"):
            return await client.execute_workflow(
                ChatOrchestrationWorkflow.run,
                ChatRequest(question="Refund my invoice and reset my password"),
                id=f"chat-{uuid.uuid4()}",
                task_queue=CHAT_QUEUE,
            )

    result = _run(_with_env(scenario))
    assert sorted(result.agents) == ["billing", "it-support"]
    assert "billing" in result.summary and "it-support" in result.summary


# ---------------------------------------------------------------- (2) golden
def test_golden_set_continues_as_new_and_is_idempotent(data_dir):
    batches = 7  # BATCHES_PER_RUN=4 => 2 個 window + 1 次收尾 => Continue-As-New 兩次
    assert batches > golden_workflows.BATCHES_PER_RUN
    seed_data.seed("demo", batches=batches, rows=30)

    async def scenario(client):
        async with worker_module.build_worker(client, "golden"):
            first = await _golden(client)  # handle.result() 會跟著 Continue-As-New 的後續 run
            second = await _golden(client, wid="golden-demo-v1-r2")  # 換 ID = 重做；輸出已存在 => skip
            return first, second

    first, second = _run(_with_env(scenario))
    assert first.batches == batches
    assert first.cases > 0
    assert second.cases == first.cases  # 冪等：重跑結果一致

    manifest = storage.get_json(first.manifest_key)
    assert len(manifest["batches"]) == batches
    assert manifest["cases"] == first.cases

    # 清洗結果：沒有 PII、batch 內沒有重複、沒有空問題（跨 batch 去重刻意不做，見 README）
    for key in storage.list_keys("golden/demo/v1/cases", suffix=".json"):
        questions = [" ".join(c["question"].lower().split()) for c in storage.get_json(key)["cases"]]
        assert len(questions) == len(set(questions))
        for q in questions:
            assert q and "@" not in q
            assert not any(phone in q for phone in ("0912", "0987", "0933"))


def test_duplicate_trigger_does_not_start_twice():
    from temporalio.common import WorkflowIDReusePolicy
    from temporalio.exceptions import WorkflowAlreadyStartedError

    seed_data.seed("demo", batches=2, rows=10)

    async def scenario(client):
        async with worker_module.build_worker(client, "golden"):
            await _golden(client)
            try:
                await client.start_workflow(
                    GoldenSetWorkflow.run,
                    GoldenSetRequest(dataset="demo", version="v1"),
                    id="golden-demo-v1",
                    task_queue=GOLDEN_QUEUE,
                    id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
                )
            except WorkflowAlreadyStartedError:
                return True
            return False

    assert _run(_with_env(scenario)) is True


# ---------------------------------------------------------------- (3) simulation
def test_simulation_good_vs_flaky_on_same_golden_version():
    seed_data.seed("demo", batches=3, rows=40)

    async def scenario(client):
        async with worker_module.build_worker(client, "golden"):
            await _golden(client)
        out = {}
        async with worker_module.build_worker(client, "simulation"):
            for variant in ("mock-good", "mock-flaky"):
                out[variant] = await client.execute_workflow(
                    SimulationWorkflow.run,
                    SimulationRequest(dataset="demo", golden_version="v1", agent_variant=variant),
                    id=f"sim-{variant}-{uuid.uuid4()}",
                    task_queue=SIM_QUEUE,
                )
        return out

    out = _run(_with_env(scenario))
    assert out["mock-good"].total == out["mock-flaky"].total > 0
    assert out["mock-good"].pass_rate == 1.0
    assert out["mock-flaky"].pass_rate < 1.0
    report = storage.get_json(out["mock-flaky"].report_key)
    assert report["pass_rate"] == out["mock-flaky"].pass_rate


def test_simulation_fails_fast_when_golden_set_missing():
    from temporalio.client import WorkflowFailureError

    async def scenario(client):
        async with worker_module.build_worker(client, "simulation"):
            try:
                await client.execute_workflow(
                    SimulationWorkflow.run,
                    SimulationRequest(dataset="nope", golden_version="v9"),
                    id=f"sim-{uuid.uuid4()}",
                    task_queue=SIM_QUEUE,
                )
            except WorkflowFailureError as e:
                return str(e.cause.cause) if e.cause else str(e)
        return None

    msg = _run(_with_env(scenario))
    assert msg and "golden set not ready" in msg  # non-retryable：不會重試 5 次才失敗


# ---------------------------------------------------------------- isolation
def test_each_role_registers_only_its_own_workflow():
    async def scenario(client):
        chat = worker_module.build_worker(client, "chat")
        golden = worker_module.build_worker(client, "golden")
        return chat.task_queue, golden.task_queue

    chat_q, golden_q = _run(_with_env(scenario))
    assert chat_q == CHAT_QUEUE and golden_q == GOLDEN_QUEUE and chat_q != golden_q
