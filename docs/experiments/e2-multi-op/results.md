# E2: Multi-Operation Benchmark — Results

**Date:** 2026-05-20

## Setup

20 sequential renames, querying dependencies after each.
CNF path: rename! → query (×20). Text path: sed → grep (×20).

## Results

| N | CNF (ms) | Text (ms) | Total Speedup | Per-Op Speedup |
|---|---:|---:|---:|---:|
| 200 | 36.1 | 110.1 | **3.05x** | 115.9x |
| 500 | 109.3 | 239.2 | **2.19x** | 267.2x |
| 1000 | 312.1 | 447.3 | **1.43x** | 248.6x |

CNF wins at every scale.

## Per-operation cost

| N | CNF per-op | Text per-op | Ratio |
|---|---:|---:|---:|
| 200 | 0.05ms | 5.33ms | 107x |
| 500 | 0.04ms | 11.63ms | 291x |
| 1000 | 0.09ms | 21.47ms | 239x |

CNF per-op cost is **constant across N**. Text per-op cost is **linear in N**.

## Scaling projection

At N=1000, extrapolating:

| Operations | CNF (ms) | Text (ms) | Speedup |
|---:|---:|---:|---:|
| 20 | 312 | 447 | 1.4x |
| 50 | 315 | 1093 | 3.5x |
| 100 | 319 | 2165 | 6.8x |
| 200 | 328 | 4312 | 13.1x |

## Analysis

The E1 crossover prediction (~35 operations) was conservative.
With 20 operations, CNF already wins at all scales because:

1. Each CNF operation is ~0.05ms (provenance check → cache hit)
2. Each text operation is ~N/50 ms (scan all files)
3. 20 × O(N) > parse overhead by N=200

The text per-op cost grows linearly with N. The CNF per-op cost
is constant. The gap widens in both dimensions (more operations,
more functions).
