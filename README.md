# LiteStore

A Redis-inspired key-value server implementing shared-nothing multi-process execution, deterministic TTL expiration via timing wheels, bounded-memory hot-key detection via Count-Min Sketch, and configurable-fsync append-only persistence.

## Architecture

LiteStore runs two listeners:

- **TCP command listener** (default `:6379`) — accepts key-value commands
- **HTTP metrics listener** (default `:9100`) — serves `/metrics` in Prometheus exposition format

Each key maps deterministically to one worker **process** via SHA-256 hash routing. Each worker process owns its own MemoryStore, TimingWheel, and AOF shard — achieving parallel execution without shared mutable state.

```text
                    +-----------------------------------+
Client (TCP) -----> | Main Process (asyncio TCP server) |
                    | parse -> route -> IPC dispatch    |
                    +----------------+------------------+
                                     |
                                     v
                       +-------------+--------------+
                       | DeterministicHashRouter    |
                       | (SHA-256 modulo partition) |
                       +-------------+--------------+
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v (Queue)                   v (Queue)                   v (Queue)
+----------------+            +----------------+          +----------------+
| Process w0     |            | Process w1     |   ...    | Process wN     |
| MemoryStore    |            | MemoryStore    |          | MemoryStore    |
| TimingWheel    |            | TimingWheel    |          | TimingWheel    |
| AOF shard w0   |            | AOF shard w1   |          | AOF shard wN   |
+----------------+            +----------------+          +----------------+

HTTP /metrics ---------> +---------------------------+
                         | MetricsCollector          |
                         | Count-Min Sketch hot keys |
                         | Prometheus exposition     |
                         +---------------------------+
```

## Request Lifecycle

```text
1. Connection handler receives one command line over TCP
2. protocol.parse_command -> CommandRequest
3. router.route_request -> owning worker process (SHA-256 mod N)
4. Main process sends WorkerRequest via multiprocessing.Queue
5. Worker process executes command against its owned MemoryStore
6. Worker appends to its per-partition AOF shard (with configurable fsync)
7. Worker sends WorkerResponse back via response queue
8. Main process records metrics (latency, throughput, hot-key via CMS)
9. protocol.serialize_response -> returned to client over TCP
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

### Multiprocessing Over Threading

Python's GIL prevents threads from achieving CPU parallelism. LiteStore uses `multiprocessing` with one process per partition:

- Each process has its own Python interpreter — no GIL contention
- IPC via `multiprocessing.Queue` pairs (request + response per worker)
- Async bridge in main process via `run_in_executor` for non-blocking queue reads
- Shared-nothing: no locks, no mutexes, no shared memory between workers

### Timing Wheel for TTL Expiration

Each worker has a timing wheel for O(1) insertion and O(1) expiration discovery:

- `EXPIRE key seconds` schedules deadline in wheel buckets
- Worker expiration cycles proactively drain due entries
- Expired keys are removed deterministically — they never linger waiting for client reads
- Contrast with Redis's probabilistic approach: sample 20 random keys, delete expired, repeat if >25% hit

### Count-Min Sketch for Hot-Key Detection

Fixed-memory probabilistic frequency estimation:

- 4 hash functions x 2048 counters = ~32KB regardless of key cardinality
- O(1) increment, O(1) frequency estimation
- Top-K tracker using min-heap alongside the sketch
- Never underestimates (can slightly overestimate due to hash collisions)

### Configurable Fsync Policy

Three durability modes for AOF persistence:

| Policy | Behavior | Trade-off |
|--------|----------|-----------|
| `never` | OS-managed flush only | Fastest writes, risk of data loss on OS crash |
| `always` | `fsync()` after every write | Safest, highest write latency |
| `every_n` | `fsync()` every N writes (default: 100) | Balanced durability and throughput |

### Per-Partition AOF Sharding

Each worker process writes its own AOF shard:

- Worker `w0` writes to `data/litestore-w0.aof`
- Worker `w1` writes to `data/litestore-w1.aof`
- Replay is per-partition on startup — each worker replays only its own shard
- Enables parallel recovery across workers
- Consistent because routing is deterministic (same key always maps to same partition)

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
PING               -> +PONG
SET key value      -> +OK
GET key            -> $value (or $-1 if missing)
DEL key            -> :1 (or :0 if missing)
EXPIRE key secs    -> :1 (or :0 if key missing)
TTL key            -> :seconds_remaining (or :-1 no expiry, :-2 missing)
```

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

87 tests covering:

- Command correctness (SET, GET, DEL, EXPIRE, TTL, PING)
- Protocol parsing and serialization
- Timing wheel expiration semantics
- Count-Min Sketch accuracy bounds
- Fsync policy behavior (mocked `os.fsync`)
- AOF persistence and crash recovery
- Worker process lifecycle and IPC
- Worker pool concurrent dispatch
- Sharding isolation and deterministic routing
- End-to-end TCP integration (socket-level)

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
