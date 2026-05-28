# Redis Clone Blueprint (LiteStore)

## 1) What You Are Building
You will build a Redis alternative that fixes Redis's core architectural limitations.

In simple words:
- Clients connect over TCP.
- They send commands like SET, GET, DEL.
- Your server stores data in RAM and replies fast.
- Persist to disk so restart does not lose data.
- Multi-threaded: breaks Redis's single-thread bottleneck.
- Deterministic TTL: expired keys never linger in memory.
- Observable: built-in metrics without external tooling.

This project proves:
- Networking & protocol design
- Concurrency & shared-nothing architecture
- Data structures (timing wheels, consistent hashing, probabilistic sketches)
- Persistence and reliability
- Production thinking (observability, benchmarks)

---

## 2) Why This Project Matters
### Resume impact
This is a high-signal systems project. It tells interviewers:
- You can build core infrastructure.
- You understand what happens below frameworks.
- You can reason about performance and reliability.

### Interview impact
You can discuss:
- Why Redis is single-threaded and how Dragonfly DB broke that limitation.
- Shared-nothing architecture vs lock-based parallelism.
- Timing wheels vs lazy expiration — O(1) vs O(n) trade-offs.
- Append-only logging and crash recovery.
- Probabilistic data structures for hot-key detection.
- Why observability should be built in, not bolted on.

---

## 3) Target Scope (What To Build)
## Phase 1 (MVP)
- TCP server
- Command parser
- Commands: PING, SET, GET, DEL
- In-memory map

## Phase 2
- TTL commands: EXPIRE, TTL
- Key expiration logic

## Phase 3
- Persistence (AOF: append-only file)
- Rebuild state on restart

## Phase 4 (Optional but strong)
- Leader-replica replication
- Basic benchmark tool + README results

## Phase 5 — Multi-Threaded Key-Space Sharding (Dragonfly-inspired)
- Partition keyspace across N worker threads using consistent hashing
- Each thread owns a slice of keys — no locks between threads
- Client connections are routed to the correct worker based on key hash
- Breaks Redis's single-thread bottleneck

## Phase 6 — Hierarchical Timing Wheel for TTL
- Replace lazy/sampling-based expiration with a timing wheel
- O(1) insertion and O(1) expiration discovery
- Keys expire precisely at their deadline — no lingering stale data
- Inspired by Linux kernel timers and Kafka's delayed message handling

## Phase 7 — Built-in Observability (Prometheus Metrics)
- /metrics HTTP endpoint in Prometheus format
- Track: p50/p99 latency per command, throughput, hot keys, memory by key prefix
- Slow query log with client attribution
- Zero-config production monitoring

---

## 4) Recommended Tech Stack
- Language: Python 3.11+
- Networking: asyncio
- Storage in memory: dict + metadata dict
- Persistence: plain text AOF log
- Tests: pytest
- Benchmarks: custom script + optional redis-benchmark comparison
- Deploy: AWS EC2 free tier + systemd service

Why Python?
- Faster learning cycle.
- Great for interviews if you can explain architecture clearly.

---

## 5) High-Level Architecture
Client
-> TCP Connection
-> Router (consistent hash on key -> pick worker thread)
-> Worker Thread N (owns its key partition)
   -> Command Parser
   -> Command Executor
   -> In-Memory Store (partition)
   -> Timing Wheel (TTL for this partition)
   -> AOF Writer (per-partition log)
-> Metrics Collector (aggregates across all workers)
-> /metrics HTTP endpoint

### Core components
1. server.py
- Accepts client connections.
- Reads command bytes.
- Sends response bytes.

2. protocol.py
- Parses incoming command format.
- Serializes server responses.

3. store.py
- Holds main key-value data.
- Holds expiry metadata.
- Exposes set/get/del/expire methods.

4. commands.py
- Maps parsed command to store operations.

5. persistence.py
- Appends write commands to log.
- Replays log on startup.

6. ttl_worker.py
- Periodically removes expired keys.

---

## 6) Suggested Project Structure
litestore/
- README.md
- requirements.txt
- .gitignore
- src/
  - main.py
  - server.py
  - router.py           (consistent hash key routing)
  - worker.py           (per-thread worker event loop)
  - protocol.py
  - commands.py
  - store.py
  - persistence.py
  - timing_wheel.py     (hierarchical timing wheel)
  - metrics.py          (prometheus metrics collector)
  - config.py
- tests/
  - test_protocol.py
  - test_commands.py
  - test_ttl.py
  - test_persistence.py
  - test_sharding.py
  - test_timing_wheel.py
  - test_metrics.py
- scripts/
  - benchmark.py
  - benchmark_compare.py  (single-thread vs multi-thread)

---

## 7) Data Model Design
### In-memory
- data: dict[str, str]
- expires_at: dict[str, float] (unix timestamp seconds)

### Rules
- GET checks if key expired before returning.
- Expired key is deleted lazily on read.
- Background sweeper also deletes expired keys proactively.

---

## 8) Command Design (Start Small)
### Must-have
- PING -> PONG
- SET key value -> OK
- GET key -> value or (nil)
- DEL key -> 1 or 0

### Next
- EXPIRE key seconds -> 1/0
- TTL key -> seconds remaining / -1 / -2

### Optional
- MGET, INCR, EXISTS

---

## 9) Protocol Strategy
Two choices:
1. Simple custom text protocol (fastest to build)
2. RESP-compatible protocol (better signal)

Recommendation:
- Start custom protocol in week 1 to get momentum.
- Upgrade to RESP in week 2.

---

## 10) Persistence (AOF) Simplified
### What is AOF?
Every write command is appended to a file.
Example lines:
- SET user:1 Snehal
- DEL user:2
- EXPIRE session:abc 300

### Startup recovery
- On startup, read file line by line.
- Replay commands in order.
- Rebuild in-memory state.

### Why this is good
- Easy to implement.
- Easy to explain.
- Good reliability story.

---

## 11) Replication (Optional Stretch)
Leader and replica model:
- Leader handles writes.
- Replica receives write stream from leader.
- Replica applies same commands.

Start minimal:
- On connect, replica asks for full sync.
- Leader sends snapshot or replay.
- Then stream incremental writes.

---

## 12) Testing Plan
### Unit tests
- Parser correctness
- Command behavior
- TTL edge cases
- AOF replay

### Integration tests
- Spin up server.
- Use socket client.
- Verify end-to-end command responses.

### Reliability tests
- Write data, kill server, restart, verify recovery.

---

## 13) Benchmark Plan
Measure:
- requests/second for SET/GET
- p50 and p95 latency
- memory usage under N keys

Publish in README table:
- Workload
- Throughput
- Latency
- Notes

Do not fake numbers.
Real but modest numbers are fine.

---

## 14) Deployment Plan (Free)
Yes, you can deploy this on AWS free tier.

### Steps
1. Launch small free-tier EC2 instance.
2. Install Python and dependencies.
3. Run server on chosen port.
4. Create systemd service for auto-restart.
5. Open security group for test IP only.

### Cost note
- Can be free under free-tier limits.
- Watch usage hours and data transfer.

---

## 15) 6-Week Roadmap
## Week 1
- Build TCP server.
- Implement PING/SET/GET/DEL.
- Write tests for commands.

## Week 2
- Add EXPIRE/TTL.
- Add background TTL sweeper.
- Improve parser/protocol.

## Week 3
- Add AOF append and replay.
- Add crash-recovery tests.
- Write benchmark script.

## Week 4
- Multi-threaded sharding: partition keys across worker threads.
- Consistent hashing for key routing.
- Benchmark single-thread vs multi-thread throughput.

## Week 5
- Hierarchical timing wheel for TTL.
- Replace lazy expiration with deterministic expiry.
- Validate zero expired keys linger beyond deadline.

## Week 6
- Prometheus /metrics endpoint.
- Per-command latency histograms, hot key tracking.
- Deploy on EC2, finalize README with architecture + benchmarks.

---

## 16) Learning Roadmap By Feature
### TCP server
Learn:
- sockets basics
- request-response lifecycle
- handling multiple clients with asyncio

### parser/protocol
Learn:
- byte streams
- framing/parsing
- malformed input handling

### store + TTL
Learn:
- hash map operations
- time-based expiry
- lazy vs active eviction

### persistence
Learn:
- write-ahead ideas
- replay for recovery
- corruption handling basics

### multi-threaded sharding
Learn:
- consistent hashing (why it minimizes key remapping)
- shared-nothing architecture (no locks = linear scaling)
- thread-safe routing (connection hand-off patterns)
- Dragonfly DB's architecture paper/blog posts

### timing wheel
Learn:
- circular buffer mechanics
- hierarchical overflow (seconds -> minutes -> hours)
- Linux kernel timer implementation (timer_wheel.c)
- comparison: O(1) wheel vs O(log n) priority queue vs O(n) sampling

### observability
Learn:
- Prometheus exposition format
- histogram bucketing for latency percentiles
- Count-Min Sketch for hot key detection
- why per-command attribution matters in production

---

## 17) Common Mistakes To Avoid
- Building too many commands too early.
- Ignoring tests until the end.
- Not handling malformed commands.
- Forgetting restart/recovery behavior.
- Over-optimizing before correctness.

---

## 18) Definition of Done
Project is done when:
- Commands work reliably across multiple worker threads.
- Multi-threaded throughput measurably beats single-threaded.
- Timing wheel expires keys deterministically (zero lingering).
- Tests pass (including sharding, timing wheel, metrics).
- Data survives restart via AOF.
- /metrics endpoint serves real latency + throughput data.
- README has architecture diagram + benchmark comparison + how to run.
- Deployed on EC2 with systemd.

---

## 19) Resume Bullet Template (After Completion)
Built a multi-threaded Redis alternative with key-space sharding (inspired by Dragonfly DB), O(1) timing-wheel TTL eviction, append-only persistence, and built-in Prometheus observability — deployed and benchmarked on AWS EC2.

---

## 20) Immediate Next 3 Actions
1. Create repository skeleton exactly as above.
2. Implement PING/SET/GET/DEL with tests.
3. Commit and tag v0.1 before adding TTL.
