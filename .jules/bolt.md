## 2026-01-29 - [Optimistic Concurrency & Crash Fix]
**Learning:** Background tasks in `brain.py` were failing because `_executor` was not defined, causing crashes. Also, Intent Analysis and Vector Search were running sequentially, adding latency.
**Action:** Defined `_executor = ThreadPoolExecutor(max_workers=4)` globally. Refactored `process_message` to submit both Intent Analysis and Vector Search to the executor immediately (Optimistic Search). This reduces latency by overlapping the IO-bound operations. Added `tests/test_brain_parallel.py` to verify.
