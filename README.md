# LiteStore

LiteStore is a Redis-inspired key-value server built as a systems project around deterministic ownership, append-only durability, timing-wheel TTL expiration, and built-in observability.

## Why This Project Is High Signal

- Demonstrates networking, concurrency, persistence, and observability in one coherent system
- Uses explicit shared-nothing ownership boundaries rather than hidden shared state
- Includes startup recovery and socket-level integration tests
- Provides benchmark scripts with real measured output

## Architecture Overview

LiteStore runtime exposes two listeners:

- TCP command listener for key-value commands
- HTTP metrics listener for `/metrics` in Prometheus format

Each key maps deterministically to one worker partition. Each worker runs its own event loop in its own thread and owns exactly one store instance.

### ASCII Architecture Diagram

```text
                    +-----------------------------------+
Client (TCP) -----> | LiteStoreRuntime (async TCP srv) |
                    | parse -> route -> worker dispatch |
                    +----------------+------------------+
                                     |
                                     v
                       +-------------+--------------+
                       | DeterministicHashRouter    |
                       +-------------+--------------+
                                     |
      +------------------------------+------------------------------+
      |                              |                              |
      v                              v                              v
+-------------+               +-------------+               +-------------+
| Worker w0   |               | Worker w1   |      ...      | Worker wN   |
| thread+loop |               | thread+loop |               | thread+loop |
| owns Store  |               | owns Store  |               | owns Store  |
| owns Wheel  |               | owns Wheel  |               | owns Wheel  |
+------+------+               +------+------+               +------+------+
       |                             |                             |
       +-----------------------------+-----------------------------+
                                     |
                                     v
                         +-----------+-----------+
                         | AOF Persistence       |
                         | append + replay JSONL |
                         +-----------------------+

HTTP /metrics ---------> +-----------------------+
                         | Metrics Endpoint      |
                         | Prometheus exposition |
                         +-----------------------+
```

## Request Lifecycle

### Command Lifecycle

```text
1) Connection handler receives one command line over TCP
2) protocol.parse_command -> CommandRequest
3) router.route_request -> owning worker id
4) runtime dispatches request to worker event loop (cross-thread safe)
5) worker executes command against owned store partition
6) successful write commands append to AOF
7) metrics collector records latency, throughput, hot-key updates
8) protocol.serialize_response -> returned to client
```

### Component Interaction Diagram

```text
Client
  | "SET user:1 alice"
  v
TCP Handler
  | parse_command
  v
CommandRequest
  | route_request(key=user:1)
  v
Worker[owning partition]
  | execute_command(request, store)
  v
CommandResponse
  | append AOF if write succeeded
  | observe metrics
  v
serialize_response
  v
Client response
```

## Worker Ownership Model

- Router computes deterministic partition from key hash
- Each worker owns one partition and one MemoryStore
- No shared mutable key-value state across workers
- Cross-thread operations use event-loop futures rather than direct state access
- Worker lifecycle is explicit: start, execute, snapshot, stop

This model preserves shared-nothing boundaries while enabling true parallel worker threads.

## Persistence Design

LiteStore uses append-only persistence (AOF) in readable JSONL:

- Writes are appended in command order
- Startup recovery replays entries in order
- Malformed replay lines are skipped safely
- Recovery routes replayed records through existing ownership/routing logic

Example entry:

```json
{"sequence": 42, "command": "SET", "args": ["user:1", "alice"]}
```

## Timing Wheel Explanation

Each worker store has a timing wheel for TTL scheduling:

- `EXPIRE key seconds` schedules deadline in wheel buckets
- Worker expiration cycles proactively drain due entries
- Expired keys are removed without waiting for client reads
- Read-time checks still act as defensive correctness fallback

TTL flow example:

```text
SET session:1 live  -> +OK
EXPIRE session:1 1  -> :1
(wait ~1s)
GET session:1       -> $-1
```

## Observability Features

Built-in metrics include:

- total command throughput
- per-command request counters
- command latency histogram buckets
- hot key access counters
- approximate memory usage by key prefix

Metrics endpoint:

- path: `/metrics`
- format: Prometheus text exposition

## Example Command Flows

### Basic CRUD

```text
PING               -> +PONG
SET user:1 alice   -> +OK
GET user:1         -> $alice
DEL user:1         -> :1
GET user:1         -> $-1
```

### Error Handling

```text
SET only_key       -> -ERR WRONG_ARITY ...
MGET user:1        -> -ERR UNKNOWN_COMMAND ...
```

## Benchmark Methodology

Benchmarks are script-driven command-layer microbenchmarks:

- workload key count: 5000
- operations: SET + GET + DEL per key
- total operations: 15000
- measured modes:
  - single-store direct command execution
  - sharded dispatch
  - threaded sharded dispatch

Important note:

- These are in-process command-path measurements, not full external socket load tests.

## Benchmark Results (Real Measurements)

Single benchmark command:

```powershell
c:/Users/SnehalDevrani/Desktop/redis/.venv/Scripts/python.exe scripts/benchmark.py --keys 5000
```

Measured result:

| workload | operations | elapsed_s | throughput_ops_s | avg_ms | p50_ms | p95_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| single-store-command-layer | 15000 | 0.0348 | 431250.11 | 0.0022 | 0.0018 | 0.0036 |

Comparison benchmark command:

```powershell
c:/Users/SnehalDevrani/Desktop/redis/.venv/Scripts/python.exe scripts/benchmark_compare.py --keys 5000 --workers 4 --concurrency 100
```

Measured results:

| mode | operations | elapsed_s | throughput_ops_s | avg_ms | p50_ms | p95_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| single-store | 15000 | 0.0304 | 493009.13 | 0.0019 | 0.0014 | 0.0035 |
| sharded-4-workers | 15000 | 0.0552 | 271823.34 | 0.0020 | 0.0016 | 0.0034 |
| threaded-sharded-4-workers | 15000 | 1.3371 | 11218.62 | 5.5854 | 5.1019 | 8.4810 |

## Tradeoff Discussions

### Shared-Nothing Ownership vs Shared Global Store

Pros:
- deterministic ownership and isolation
- easier reasoning about race boundaries

Tradeoff:
- cross-thread dispatch overhead and snapshot aggregation cost

### JSONL AOF vs Binary Log

Pros:
- readable and debuggable
- simple replay semantics

Tradeoff:
- larger storage footprint and lower compactness

### Threaded Worker Event Loops

Pros:
- true parallel worker execution model
- preserves architecture boundaries

Tradeoff:
- cross-thread scheduling overhead currently dominates microbenchmark latency in threaded mode

## Limitations

- Custom text protocol only (not RESP-compatible yet)
- Replication is not implemented
- AOF durability tuning and compaction strategy are minimal
- Timing wheel is deterministic but not full hierarchical multi-level yet
- Benchmark suite is microbenchmark-focused, not full socket load benchmarking
- Production hardening (auth, TLS, backups, ACLs) is not complete

## Future Improvements

- RESP protocol compatibility
- replication and failover
- AOF rewrite/compaction and fsync policy controls
- richer observability (slow query logs, p99-first reporting)
- production-grade external load testing harness
- security hardening (authentication, ACLs, TLS)

## How to Run Locally

### Prerequisites

- Python 3.11+
- virtual environment at `.venv`

### Install dependencies

```powershell
c:/Users/SnehalDevrani/Desktop/redis/.venv/Scripts/python.exe -m pip install pytest pytest-asyncio
```

### Run server

```powershell
c:/Users/SnehalDevrani/Desktop/redis/.venv/Scripts/python.exe src/main.py --host 127.0.0.1 --port 6379 --metrics-host 127.0.0.1 --metrics-port 9100 --workers 4 --aof-path data/litestore.aof
```

### Run tests

```powershell
c:/Users/SnehalDevrani/Desktop/redis/.venv/Scripts/python.exe -m pytest -q
```

## How to Run Benchmarks

```powershell
c:/Users/SnehalDevrani/Desktop/redis/.venv/Scripts/python.exe scripts/benchmark.py --keys 5000
c:/Users/SnehalDevrani/Desktop/redis/.venv/Scripts/python.exe scripts/benchmark_compare.py --keys 5000 --workers 4 --concurrency 100
```

## Deployment Instructions (EC2 + systemd)

### 1) Provision instance

- Launch Ubuntu EC2 instance
- Open only required inbound ports for trusted sources (app and metrics)

### 2) Install runtime dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
```

### 3) Clone and prepare

```bash
git clone <your-repo-url> litestore
cd litestore
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip pytest pytest-asyncio
```

### 4) Create systemd unit

Example `/etc/systemd/system/litestore.service`:

```ini
[Unit]
Description=LiteStore Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/litestore
ExecStart=/home/ubuntu/litestore/.venv/bin/python src/main.py --host 0.0.0.0 --port 6379 --metrics-host 0.0.0.0 --metrics-port 9100 --workers 4 --aof-path data/litestore.aof
Restart=always
RestartSec=3
User=ubuntu

[Install]
WantedBy=multi-user.target
```

### 5) Enable and run

```bash
sudo systemctl daemon-reload
sudo systemctl enable litestore
sudo systemctl start litestore
sudo systemctl status litestore
```

### 6) Verify

- TCP command endpoint responds to `PING`
- `http://<host>:9100/metrics` returns Prometheus metrics
- AOF file grows on writes and restores state after service restart

Deployment bundle in this repository:

- `deploy/litestore.service`
- `deploy/litestore.env.example`
- `deploy/litestore.logrotate`
- `scripts/deploy_ec2.sh`
- `scripts/install_systemd.sh`
- `scripts/start_prod.sh`
- `docs/deployment.md`
- `docs/operations.md`

## Source of Truth

Project blueprint and scope are defined in `redis.md`.
