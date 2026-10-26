# Kimi-6.1 Latency Benchmark Test Plan

## Overview

**Objective:** Measure and compare inference latency of Kimi-6.1 across single-node and dual-node deployments under a fixed long-context, fixed-throughput workload.

**Audience:** This document is to be executed by team members. Results must be recorded in the result tables for validation.

---

## Hardware Configurations

| Config ID | Description         | Nodes | GPUs per Node | Total GPUs | Interconnect     |
|-----------|---------------------|-------|----------------|------------|------------------|
| `CFG-1`   | Single Node         | 1     | H200 × 8       | 8          | NVLink (intra)   |
| `CFG-2`   | Dual Node           | 2     | H200 × 8       | 16         | NVIDIA InfiniBand|

> **CFG-2 note:** Nodes are connected via NVIDIA InfiniBand. Record the IB link speed and topology (e.g., HDR 200 Gb/s, single-switch) at test time.

---

## Static Parameters (Fixed Across All Test Cases)

| Parameter         | Value          | Notes                                  |
|-------------------|----------------|----------------------------------------|
| Input token length | 100,000 tokens | Pad/truncate prompt to exactly 100K    |
| Request rate      | 200 req/min    | ≈ 3.33 req/s sustained                 |
| Model             | Kimi-6.1       | Pin to exact checkpoint/version        |
| Precision         | BF16           | Confirm with serving framework config  |
| Serving framework | (fill in)      | e.g., vLLM, TGI, SGLang               |
| Test duration     | 10 min warm-up + 20 min measurement | Discard warm-up data  |

---

## Variable Parameters (Per Test Case)

The only variable across test cases is **output token length**. All other parameters remain static.

| Variable         | Values Tested                  |
|------------------|-------------------------------|
| Output tokens    | 128 / 512 / 1024 / 2048       |

This yields **4 scenarios × 2 configs = 8 test cases total**.

---

## Metrics to Collect

For each test case, record all metrics below at **P50, P90, and P99** percentiles.

| Metric | Abbreviation | Unit   | Description                                      |
|--------|-------------|--------|--------------------------------------------------|
| Time to First Token    | TTFT | ms  | Latency from request sent to first output token received |
| Time Between Tokens    | TBT  | ms  | Average inter-token latency (decode step)        |
| End-to-End Latency     | E2E  | ms  | Total time from request to last output token     |
| Output Throughput      | OTP  | tok/s | Total output tokens generated per second (system-level) |
| Request Success Rate   | RSR  | %   | % of requests completed without error or timeout |
| GPU Memory Used        | GMEM | GB  | Peak HBM usage per GPU during measurement window |
| GPU Utilization        | GUTIL| %   | Average GPU compute utilization during measurement|

---

## Test Cases

### TC-01 — CFG-1 · Output 128 tokens

| Field              | Value           |
|--------------------|-----------------|
| Config             | CFG-1 (1 node, 8× H200) |
| Input tokens       | 100,000         |
| Output tokens      | 128             |
| Request rate       | 200 req/min     |

### TC-02 — CFG-1 · Output 512 tokens

| Field              | Value           |
|--------------------|-----------------|
| Config             | CFG-1 (1 node, 8× H200) |
| Input tokens       | 100,000         |
| Output tokens      | 512             |
| Request rate       | 200 req/min     |

### TC-03 — CFG-1 · Output 1024 tokens

| Field              | Value           |
|--------------------|-----------------|
| Config             | CFG-1 (1 node, 8× H200) |
| Input tokens       | 100,000         |
| Output tokens      | 1024            |
| Request rate       | 200 req/min     |

### TC-04 — CFG-1 · Output 2048 tokens

| Field              | Value           |
|--------------------|-----------------|
| Config             | CFG-1 (1 node, 8× H200) |
| Input tokens       | 100,000         |
| Output tokens      | 2048            |
| Request rate       | 200 req/min     |

### TC-05 — CFG-2 · Output 128 tokens

| Field              | Value           |
|--------------------|-----------------|
| Config             | CFG-2 (2 nodes, 16× H200, InfiniBand) |
| Input tokens       | 100,000         |
| Output tokens      | 128             |
| Request rate       | 200 req/min     |

### TC-06 — CFG-2 · Output 512 tokens

| Field              | Value           |
|--------------------|-----------------|
| Config             | CFG-2 (2 nodes, 16× H200, InfiniBand) |
| Input tokens       | 100,000         |
| Output tokens      | 512             |
| Request rate       | 200 req/min     |

### TC-07 — CFG-2 · Output 1024 tokens

| Field              | Value           |
|--------------------|-----------------|
| Config             | CFG-2 (2 nodes, 16× H200, InfiniBand) |
| Input tokens       | 100,000         |
| Output tokens      | 1024            |
| Request rate       | 200 req/min     |

### TC-08 — CFG-2 · Output 2048 tokens

| Field              | Value           |
|--------------------|-----------------|
| Config             | CFG-2 (2 nodes, 16× H200, InfiniBand) |
| Input tokens       | 100,000         |
| Output tokens      | 2048            |
| Request rate       | 200 req/min     |

---

## Results Table

> **Instructions for executors:** Fill in every cell. If a metric cannot be measured, write `N/A` and add a note. Do not leave cells blank.

### TTFT (ms) — Time to First Token

| TC    | Config | Output Tokens | P50 | P90 | P99 | Notes |
|-------|--------|---------------|-----|-----|-----|-------|
| TC-01 | CFG-1  | 128           |     |     |     |       |
| TC-02 | CFG-1  | 512           |     |     |     |       |
| TC-03 | CFG-1  | 1024          |     |     |     |       |
| TC-04 | CFG-1  | 2048          |     |     |     |       |
| TC-05 | CFG-2  | 128           |     |     |     |       |
| TC-06 | CFG-2  | 512           |     |     |     |       |
| TC-07 | CFG-2  | 1024          |     |     |     |       |
| TC-08 | CFG-2  | 2048          |     |     |     |       |

### TBT (ms) — Time Between Tokens (Decode Latency)

| TC    | Config | Output Tokens | P50 | P90 | P99 | Notes |
|-------|--------|---------------|-----|-----|-----|-------|
| TC-01 | CFG-1  | 128           |     |     |     |       |
| TC-02 | CFG-1  | 512           |     |     |     |       |
| TC-03 | CFG-1  | 1024          |     |     |     |       |
| TC-04 | CFG-1  | 2048          |     |     |     |       |
| TC-05 | CFG-2  | 128           |     |     |     |       |
| TC-06 | CFG-2  | 512           |     |     |     |       |
| TC-07 | CFG-2  | 1024          |     |     |     |       |
| TC-08 | CFG-2  | 2048          |     |     |     |       |

### E2E Latency (ms) — End-to-End Request Latency

| TC    | Config | Output Tokens | P50 | P90 | P99 | Notes |
|-------|--------|---------------|-----|-----|-----|-------|
| TC-01 | CFG-1  | 128           |     |     |     |       |
| TC-02 | CFG-1  | 512           |     |     |     |       |
| TC-03 | CFG-1  | 1024          |     |     |     |       |
| TC-04 | CFG-1  | 2048          |     |     |     |       |
| TC-05 | CFG-2  | 128           |     |     |     |       |
| TC-06 | CFG-2  | 512           |     |     |     |       |
| TC-07 | CFG-2  | 1024          |     |     |     |       |
| TC-08 | CFG-2  | 2048          |     |     |     |       |

### System Metrics (per test case, averaged over measurement window)

| TC    | Config | Output Tokens | OTP (tok/s) | RSR (%) | GMEM (GB/GPU) | GUTIL (%) | Notes |
|-------|--------|---------------|-------------|---------|---------------|-----------|-------|
| TC-01 | CFG-1  | 128           |             |         |               |           |       |
| TC-02 | CFG-1  | 512           |             |         |               |           |       |
| TC-03 | CFG-1  | 1024          |             |         |               |           |       |
| TC-04 | CFG-1  | 2048          |             |         |               |           |       |
| TC-05 | CFG-2  | 128           |             |         |               |           |       |
| TC-06 | CFG-2  | 512           |             |         |               |           |       |
| TC-07 | CFG-2  | 1024          |             |         |               |           |       |
| TC-08 | CFG-2  | 2048          |             |         |               |           |       |

---

## Environment Checklist (Fill Before Each Run)

Executors must complete this checklist and attach it to results.

| Item                          | CFG-1 Value | CFG-2 Value |
|-------------------------------|-------------|-------------|
| Model checkpoint commit/tag   |             |             |
| Serving framework + version   |             |             |
| Driver version (CUDA)         |             |             |
| OS / kernel version           |             |             |
| IB link speed (CFG-2 only)    | N/A         |             |
| IB topology (CFG-2 only)      | N/A         |             |
| Tensor parallel degree (TP)   |             |             |
| Pipeline parallel degree (PP) |             |             |
| KV cache utilization at end   |             |             |
| Load generator tool + version |             |             |
| Run date / time               |             |             |
| Executor name                 |             |             |

---

## Validation Criteria

The reviewer (plan owner) will validate results against the following rules. Any failing check must be investigated before results are accepted.

| # | Check | Pass Condition |
|---|-------|----------------|
| V1 | Request success rate | RSR ≥ 99% for all test cases |
| V2 | TTFT scaling with output length | TTFT should be roughly constant across output lengths within the same config (prefill-dominated at 100K input) |
| V3 | TBT stability | TBT P99 / P50 ratio ≤ 3× (no severe tail latency) |
| V4 | Dual-node TTFT | CFG-2 TTFT should be within 20% of CFG-1 TTFT (IB adds minimal prefill overhead) |
| V5 | Dual-node TBT | CFG-2 TBT should be ≤ CFG-1 TBT (more GPUs = faster decode) |
| V6 | GPU memory headroom | Peak GMEM < 90% of 80 GB HBM3 per GPU |
| V7 | Reproducibility | If a case is re-run, P50 values must agree within ±5% |

---

## Notes & Known Risks

- **100K input at 200 req/min is a high KV-cache pressure workload.** Monitor KV cache eviction rate; if evictions occur, note it and flag results as potentially degraded.
- **InfiniBand topology matters.** Single-switch vs. multi-hop can significantly affect all-reduce latency in CFG-2. Record topology in the environment checklist.
- **Warm-up is mandatory.** The first 10 minutes of traffic are discarded because JIT compilation and KV cache warmup inflate early latency.
- **Load generator must honor 200 req/min exactly.** Use a rate-limited client (e.g., `locust`, `wrk2`, or a custom Poisson-process script). Do not use a fixed-concurrency client as a proxy for throughput.
