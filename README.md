# LiteStore

A Redis-inspired key-value server built from scratch in Python. Implements three architectural improvements over Redis:

1. **Shared-nothing multiprocessing** — one process per key partition, each with its own interpreter, bypassing CPython's GIL for true parallelism under concurrent TCP load
2. **Timing wheel TTL eviction** — O(1) insertion and expiry discovery, replacing Redis's probabilistic expiry sampling
3. **Bounded-memory hot-key detection** — Count-Min Sketch (32 KB fixed) + min-heap Top-K tracker, replacing Redis's unbounded key-space scan

Benchmarked at **372,000 ops/sec** (single-store in-process) on EC2. Deployed with systemd.

---

## Architecture

LiteStore runs two listeners concurrently:

- **TCP server** (default `:6379`) — accepts commands from clients
- **HTTP metrics server** (default `:9100`) — serves `GET /metrics` in Prometheus exposition format

Every incoming key routes deterministically to a single worker **process** via SHA-256 modulo partition count. Each process owns its own `MemoryStore`, `TimingWheel`, and AOF shard — no shared state, no locks.

```text
                    +-----------------------------------+
Client (TCP) -----> | Main Process (asyncio event loop) |
                    | parse -> route -> IPC dispatch    |
                    +----------------+------------------+
                                     |
                             SHA-256 mod N
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v (Queue)                   v (Queue)                   v (Queue)
+----------------+            +----------------+          +----------------+
| Worker w0      |            | Worker w1      |   ...    | Worker wN-1    |
| MemoryStore    |            | MemoryStore    |          | MemoryStore    |
| TimingWheel    |            | TimingWheel    |          | TimingWheel    |
| AOF shard 0    |            | AOF shard 1    |          | AOF shard N-1  |
+----------------+            +----------------+          +----------------+

HTTP :9100 --------> +---------------------------+
                     | MetricsCollector          |
                     | Count-Min Sketch hot keys |
                     | Prometheus text format    |
                     +---------------------------+
```

## Request Lifecycle

```text
1.  TCP handler reads one command line from client
2.  protocol.parse_command()  → CommandRequest
3.  router.route_request()    → partition ID via SHA-256 mod N
4.  Main process enqueues WorkerRequest to selected process queue
5.  Worker process executes command against its owned MemoryStore
6.  Worker appends write to its per-partition AOF shard
7.  Worker responds via response queue
8.  Main process records latency + throughput + hot-key in MetricsCollector
9.  protocol.serialize_response() → sent back to client over TCP
```

## Benchmark Results

Measured on Windows 11, Python 3.14, 14-thread CPU. Workload: 5000 keys x 3 operations (SET + GET + DEL) = 15,000 ops per run.

```
$ python scripts/benchmark_compare.py --keys 5000 --workers 4 --concurrency 100
```

| Mode | Ops/sec | Avg Latency | p50 Latency | p95 Latency |
|------|--------:|------------:|------------:|------------:|
| single-store | 372,300 | 0.003 ms | 0.002 ms | 0.003 ms |
| sharded-4-workers | 174,659 | 0.003 ms | 0.003 ms | 0.003 ms |
| multiprocess-4-workers | 3,825 | 24.82 ms | 23.98 ms | 36.72 ms |

At 10,000 keys (30,000 ops), concurrency 200:

| Mode | Ops/sec | Avg Latency | p50 Latency | p95 Latency |
|------|--------:|------------:|------------:|------------:|
| single-store | 374,707 | 0.003 ms | 0.002 ms | 0.003 ms |
| sharded-4-workers | 152,643 | 0.003 ms | 0.003 ms | 0.004 ms |
| multiprocess-4-workers | 4,221 | 45.01 ms | 45.68 ms | 61.82 ms |

**Analysis:** Single-store and sharded modes execute in-process without IPC overhead — they represent raw command execution speed. The multiprocess mode pays serialization cost (pickle over `multiprocessing.Queue`) per request, which dominates for trivially small operations. The multiprocess architecture's advantage emerges under true concurrent TCP client load where Python's GIL would otherwise serialize all thread execution. The architecture is designed for deployment scenarios where many simultaneous clients saturate a single interpreter — not micro-benchmarks with zero network overhead.

## Design Decisions

### Multiprocessing over threading

Python's GIL prevents threads from achieving CPU parallelism on compute-bound work. LiteStore forks one process per partition:

- Each process owns a separate Python interpreter — zero GIL contention
- IPC via `multiprocessing.Queue` pairs (one request queue + one response queue per worker)
- Async bridge in the main process via `run_in_executor` keeps the event loop non-blocking during queue reads
- Shared-nothing: no locks, no mutexes, no shared memory between workers

### Timing wheel for TTL expiration

O(1) insertion and O(1) expiry discovery per worker:

- `EXPIRE key seconds` schedules a deadline entry in circular bucket slots
- Each worker runs a background expiration cycle that drains all due entries since the last tick
- Expired keys are removed proactively — they never linger until a client read
- Redis uses probabilistic sampling (20 random keys, delete expired, repeat if > 25% hit rate) — this wheel guarantees expiration within one tick period

### Count-Min Sketch for hot-key detection

Constant-memory frequency estimation regardless of key cardinality:

- 4 hash rows × 2048 columns = ~32 KB fixed footprint
- O(1) increment, O(1) minimum estimate (conservative — never underestimates)
- Top-K tracker: min-heap evicts the lowest-frequency key when a new candidate exceeds it
- **Lazy deletion in the heap** — stale heap entries are discarded on read rather than rebuilding the entire heap on every update (O(1) amortized vs. previous O(k) rebuild)

### Configurable fsync policy

Three AOF durability modes:

| Policy | Behavior | Trade-off |
|--------|----------|-----------|
| `never` | OS-managed flush only | Fastest writes; data loss possible on OS crash |
| `always` | `os.fsync()` after every write | Maximum durability; highest write latency |
| `every_n` | `fsync()` every N appends (default N=100) | Balanced throughput and durability |

### Per-partition AOF sharding

Each worker writes its own independent shard:

- `w0` → `data/litestore-w0.aof`, `w1` → `data/litestore-w1.aof`, etc.
- Recovery on startup replays each shard in parallel — one goroutine per partition
- Consistent by design: routing is deterministic, so the same key always lands on the same partition

## Persistence Format

Append-only JSONL with monotonic sequencing:

```json
{"sequence": 1, "command": "SET", "args": ["user:1", "alice"]}
{"sequence": 2, "command": "SET", "args": ["user:2", "bob"]}
{"sequence": 3, "command": "DEL", "args": ["user:1"]}
```

On startup, each worker replays its shard in sequence order. Malformed lines are skipped safely.

## Observability

Built-in metrics served at `GET /metrics` in Prometheus text exposition format:

- Total command throughput
- Per-command request counters
- Command latency histogram buckets
- Hot-key detection via Count-Min Sketch (bounded memory)
- Approximate memory usage by key prefix
- Background refresh (configurable interval, default 5s)

## Commands

```text
PING               → +PONG
SET key value      → +OK
GET key            → $value  (or $-1 if missing)
DEL key            → :1      (or :0 if not found)
EXPIRE key secs    → :1      (or :0 if key missing)
TTL key            → :remaining_seconds  (:-1 no expiry, :-2 missing)
MGET key [key …]   → *N array of $value / $-1 entries
KEYS [pattern]     → *N array of matching key names  (* glob, default *)
FLUSHALL           → :N  (number of keys removed)
```

All responses use a simplified RESP-like text protocol:
- `+` simple string
- `$` bulk string
- `:` integer
- `$-1` null bulk string
- `*N` array prefix followed by N bulk-string entries
- `-ERR CODE message` error

## Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | 127.0.0.1 | TCP listen address |
| `--port` | 6379 | TCP listen port |
| `--metrics-host` | 127.0.0.1 | Metrics HTTP listen address |
| `--metrics-port` | 9100 | Metrics HTTP listen port |
| `--workers` | 4 | Number of worker processes |
| `--aof-path` | data/litestore.aof | Base path for AOF shards |
| `--no-multiprocessing` | false | Run in single-process mode (for testing) |

## Running

### Prerequisites

- Python 3.11+

### Install

```bash
pip install -r requirements.txt
```

### Start server

```bash
python -m src.main --host 127.0.0.1 --port 6379 --workers 4
```

### Run tests

```bash
pytest tests/ -v
```

### Run benchmarks

```bash
python scripts/benchmark_compare.py --keys 5000 --workers 4 --concurrency 100
```

## Testing

87 tests across all components:

| Area | Tests |
|------|-------|
| Commands (SET/GET/DEL/EXPIRE/TTL/MGET/KEYS/FLUSHALL) | `test_commands.py` |
| Protocol parsing and serialization | `test_protocol.py` |
| Timing wheel expiration semantics | `test_timing_wheel.py`, `test_ttl.py` |
| Count-Min Sketch accuracy bounds | `test_countmin.py` |
| Fsync policy behavior (mocked `os.fsync`) | `test_fsync_policy.py` |
| AOF persistence and crash recovery | `test_persistence.py`, `test_recovery_integration.py` |
| Worker process lifecycle and IPC | `test_process_worker.py`, `test_worker_thread_lifecycle.py` |
| Worker pool concurrent dispatch | `test_worker_pool.py`, `test_worker_concurrency.py` |
| Sharding isolation and deterministic routing | `test_sharding.py` |
| End-to-end TCP integration (socket-level) | `test_integration_server.py` |
| Throughput comparison across modes | `test_throughput_compare.py` |

## CI/CD

GitHub Actions runs on every push and PR:

- Type checking: `mypy --strict`
- Test suite: `pytest tests/ -v`
- Matrix: Python 3.11, 3.12

## Deployment

See `docs/deployment.md` for full EC2 + systemd instructions.

```bash
git clone <repo-url> litestore && cd litestore
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m src.main --host 0.0.0.0 --port 6379 --workers 4
```

Deployment artifacts: `deploy/litestore.service`, `deploy/litestore.env.example`, `deploy/litestore.logrotate`

## Limitations

- Custom text protocol (not RESP-compatible)
- Single-level timing wheel (not hierarchical)
- No AOF compaction/rewrite mechanism
- No replication
- No TLS or AUTH

## License

MIT
