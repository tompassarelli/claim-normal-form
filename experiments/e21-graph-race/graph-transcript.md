**Step 10 PASS** — the failed run from step 3 is still queryable in the graph:
- Run entity: **1240**
- Status: **error**
- Reason: **`/: division by zero`** ✓

---

## Full Summary

| Step | Task | Result | Status |
|------|------|--------|--------|
| 1 | Parse 5 functions | base-rate, overtime, total-pay, split-pay, after-split (IDs 222–469) | **PASS** |
| 2 | split-pay(1000, 4) baseline | 250 | **PASS** |
| 3 | split-pay(1000, 0) crash | Error: `/: division by zero` (run 1240) | **PASS** |
| 4 | Add safe-div | Added as id 1327 | **PASS** |
| 5 | Wire safe-div into split-pay | split-pay body replaced, entity 415 preserved | **PASS** |
| 6a | split-pay(1000, 4) after fix | 250 | **PASS** |
| 6b | split-pay(1000, 0) after fix | 0 (no crash) | **PASS** |
| 6c | after-split(1000, 4, 50) | 200 | **PASS** |
| 7 | Dependencies of safe-div | split-pay (415) | **PASS** |
| 8 | Rename safe-div → guarded-div | Render shows `guarded-div` | **PASS** |
| 9 | after-split after rename | 200 | **PASS** |
| 10 | Error history queryable | Run 1240, status=error, reason=`/: division by zero` | **PASS** |

All 10 steps pass. The graph preserved the full history — the error run from step 3 remained queryable even after the bug was fixed, the function was modified, and the dependency renamed.
