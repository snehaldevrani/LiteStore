# LiteStore

LiteStore is a Redis-inspired key-value server built as a systems project around deterministic ownership, append-only durability, timing-wheel TTL expiration, and built-in observability.

## Why This Project Is High Signal

- Demonstrates networking, concurrency, persistence, and observability in one coherent system
- Uses multiprocessing with shared-nothing architecture to bypass Python's GIL for true parallelism
- Implements a Count-Min Sketch for bounded-memory hot-key detection
- Implements a timing wheel for O(1) deterministic TTL expiration
- Includes startup recovery and socket-level integration tests
- Provides benchmark scripts with real measured output

## Architecture Overview

LiteStore runtime exposes two listeners:

- TCP command listener for key-value commands
- HTTP metrics listener for `/metrics` in Prometheus format

Each key maps deterministically to one worker **process**. Each worker process owns its own MemoryStore, TimingWheel, and AOF shard — achieving true parallel execution without the GIL.

### Architecture Diagram

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
1) Connection handler receives one command line over TCP
2) protocol.parse_command -> CommandRequest
3) router.route_request -> owning worker process
4) Main process sends WorkerRequest via multiprocessing.Queue
5) Worker process executes command against its owned store
6) Worker appends to its per-partition AOF shard (with configurable fsync)
7) Worker sends WorkerResponse back via response queue
8) Main process records metrics (latency, throughput, hot-key via CMS)
9) protocol.serialize_response -> returned to client
```

## Key Design Decisions

### Multiprocessing Over Threading

Python's GIL prevents threads from achieving true CPU parallelism. LiteStore uses `multiprocessing` with one process per partition:
- Each process has its own Python interpreter — no GIL contention
- IPC via `multiprocessing.Queue` pairs (request + response per worker)
- Async bridge in main process via `run_in_executor` for non-blocking queue reads
- Shared-nothing: no locks, no mutexes, no shared memory between workers

### Count-Min Sketch for Hot-Key Detection

Instead of an unbounded Counter that grows with every unique key:
- Fixed-memory data structure: 4 hash functions × 2048 counters = ~32KB
- O(1) increment and O(1) frequency estimation
- Top-K tracker using min-heap alongside the sketch
- Memory stays constant regardless of key cardinality

### Configurable Fsync Policy

Three durability modes for AOF persistence:
- `never`: flush only (fastest, risk of data loss on OS crash)
- `always`: fsync after every write (safest, highest latency)
- `every_n`: fsync every N writes (balanced, default N=100)

### Per-Partition AOF Sharding

Each worker process writes its own AOF shard file:
- Worker `w0` → `data/litestore-w0.aof`
- Worker `w1` → `data/litestore-w1.aof`
- Replay is per-partition on startup — each worker only replays its own shard
- Consistent because routing is deterministic (same key → same partition always)

## Worker Ownership Model

- Router computes deterministic partition from SHA-256 key hash
- Each worker process owns one partition, one MemoryStore, one TimingWheel
- No shared mutable key-value state across workers
- Worker lifecycle is explicit: start, execute, shutdown

## Persistence Design

LiteStore uses append-only persistence (AOF) in readable JSONL:

- Writes are appended in command order per partition
- Startup recovery replays entries in order
- Malformed replay lines are skipped safely
- Configurable fsync policy for durability guarantees

Example entry:

```json
{"sequence": 42, "command": "SET", "args": ["user:1", "alice"]}
```

## Timing Wheel

Each worker store has a timing wheel for TTL scheduling:

- `EXPIRE key seconds` schedules deadline in wheel buckets
- Worker expiration cycles proactively drain due entries
- Expired keys are removed without waiting for client reads
- O(1) insertion and O(1) expiration discovery

## Observability Features

Built-in metrics include:

- Total command throughput
- Per-command request counters
- Command latency histogram buckets (Prometheus format)
- Hot key detection via Count-Min Sketch (bounded memory)
- Approximate memory usage by key prefix
- Periodic background refresh (configurable interval, default 5s)

Metrics endpoint:

- Path: `/metrics`
- Format: Prometheus text exposition

## Benchmark Methodology

Benchmarks are script-driven command-layer microbenchmarks:

- Workload: 5000 keys × 3 operations (SET + GET + DEL) = 15000 ops
- Measured modes:
  - **single-store**: direct command execution (baseline)
  - **sharded**: partitioned dispatch, single process (routing overhead)
  - **multiprocess**: separate worker processes with IPC (true parallelism)

Run benchmarks:

```bash
python scripts/benchmark_compare.py --keys 5000 --workers 4 --concurrency 100
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
| `--no-multiprocessing` | false | Run in single-process mode |

## Example Command Flows

### Basic CRUD

```text
PING               -> +PONG
SET user:1 alice   -> +OK
GET user:1         -> $alice
DEL user:1         -> :1
GET user:1         -> $-1
```

### TTL

```text
SET session:1 live    -> +OK
EXPIRE session:1 60   -> :1
TTL session:1         -> :59
```

### Error Handling

```text
SET only_key       -> -ERR WRONG_ARITY ...
MGET user:1        -> -ERR UNKNOWN_COMMAND ...
```

## Tradeoff Discussions

### Multiprocessing vs Threading

- **Multiprocessing**: True parallelism, bypasses GIL, higher IPC overhead per request
- **Threading**: Lower dispatch overhead but GIL prevents parallel CPU execution
- **Decision**: Multiprocessing wins for workloads with many concurrent clients where each request does meaningful work

### Count-Min Sketch vs Exact Counter

- **CMS**: O(1) operations, fixed memory, slight overestimation possible
- **Exact Counter**: Perfect accuracy but unbounded memory growth
- **Decision**: CMS for production safety; overestimation is acceptable for hot-key detection

### JSONL AOF vs Binary Log

- Readable, debuggable, simple replay semantics
- Tradeoff: larger storage footprint than binary format

## Limitations

- Custom text protocol only (not RESP-compatible yet)
- Replication is not implemented
- Timing wheel is single-level (not hierarchical)
- No AOF compaction/rewrite mechanism
- Production hardening (auth, TLS, ACLs) is not complete

## How to Run

### Prerequisites

- Python 3.11+

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run server

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

## CI/CD

GitHub Actions workflow runs on every push/PR:
- Type checking with mypy (strict mode)
- Full test suite with pytest
- Matrix: Python 3.11, 3.12

## Deployment (EC2 + systemd)

See `docs/deployment.md` for full instructions. Quick start:

```bash
git clone <your-repo-url> litestore && cd litestore
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m src.main --host 0.0.0.0 --port 6379 --workers 4
```

Deployment artifacts: `deploy/litestore.service`, `deploy/litestore.env.example`, `deploy/litestore.logrotate`

## Resume Bullet

Built a multi-process Redis alternative with shared-nothing key-space sharding (Dragonfly-inspired), O(1) timing-wheel TTL eviction, Count-Min Sketch hot-key detection, configurable-fsync AOF persistence, and built-in Prometheus observability — deployed and benchmarked on AWS EC2.

