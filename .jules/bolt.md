## 2026-01-19 - [Firestore Deduplication Optimization]
**Learning:** Replacing a read-then-write pattern (`get().exists` + `set()`) with an atomic `create()` operation (catching `AlreadyExists`) reduces database round-trips by 50% for new records and eliminates race conditions.
**Action:** Always prefer atomic operations like `create()` or `update()` over `get()` + logic + `set()` when consistency or latency is a concern.
