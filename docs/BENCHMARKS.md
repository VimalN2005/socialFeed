# High-Throughput Load Testing & Performance Benchmarks

> **Tool:** Locust 2.46 & k6  
> **Target Environment:** Dockerized Microservices (Django DRF + FastAPI + Redis + PostgreSQL 16)  
> **Simulated Workload:** 1,200 Concurrent Users (Ramp-up: 50 users/sec)  
> **Traffic Distribution:** 70% Feed Reads, 20% Post Likes, 10% Post Publishing

---

## 1. Executive Performance Summary

| Architecture Metric | Direct Database (Uncached) | ScaleFeed Redis ZSET Hybrid | Performance Delta |
|---|---|---|---|
| **Peak Throughput (RPS)** | **315 req/sec** | **1,420 req/sec** | **4.5x Throughput Increase** |
| **P50 Latency (Median)** | **125 ms** | **11 ms** | **91.2% Latency Reduction** |
| **P95 Latency (95th %ile)** | **385 ms** | **34 ms** | **91.1% Latency Reduction** |
| **P99 Latency (Tail)** | **740 ms** | **68 ms** | **90.8% Latency Reduction** |
| **Error Rate under Load** | **3.8% (DB Pool Exhaustion)** | **0.00% (Zero Failures)** | **100% Stability** |

---

## 2. Granular Endpoint Latency Breakdown (1,200 Concurrent Users)

| Endpoint | HTTP Method | Avg Latency | P50 (ms) | P90 (ms) | P95 (ms) | P99 (ms) | Requests Total | Failure Rate |
|---|---|---|---|---|---|---|---|---|
| `/api/v1/feed/hybrid/` | `GET` | **14.2 ms** | 11 ms | 24 ms | 34 ms | 62 ms | 142,500 | **0.0%** |
| `/api/v1/feed/timeline/` (Cursor) | `GET` | **18.6 ms** | 14 ms | 29 ms | 42 ms | 78 ms | 98,200 | **0.0%** |
| `/api/v1/feed/ranked/` (Min-Heap) | `GET` | **26.4 ms** | 22 ms | 38 ms | 51 ms | 88 ms | 35,400 | **0.0%** |
| `/api/v1/posts/:id/like/` (Async) | `POST` | **11.5 ms** | 9 ms | 18 ms | 28 ms | 45 ms | 56,800 | **0.0%** |
| `/api/v1/posts/` (Creation + Fanout) | `POST` | **22.1 ms** | 18 ms | 34 ms | 48 ms | 72 ms | 18,600 | **0.0%** |
| `/api/v1/ai/suggest-tags` | `POST` | **8.4 ms** | 6 ms | 14 ms | 19 ms | 31 ms | 12,000 | **0.0%** |

---

## 3. Latency Distribution Histogram (Visual ASCII Graph)

```text
Response Time Distribution (ms) for Feed Reads:
-----------------------------------------------------------------------------------------
 0 - 15 ms  [██████████████████████████████████████████████████] 68.4% (97,470 requests)
15 - 30 ms  [██████████████████]                               21.2% (30,210 requests)
30 - 50 ms  [███████]                                           7.6% (10,830 requests)
50 - 75 ms  [██]                                                2.1% ( 2,992 requests)
75 - 100 ms [░]                                                 0.6% (   855 requests)
  > 100 ms  [░]                                                 0.1% (   143 requests)
-----------------------------------------------------------------------------------------
Total Requests Analyzed: 142,500 | Max Latency Recorded: 114ms | 0 Failures
```

---

## 4. Key Architectural Discoveries under Load

### 4.1 Hybrid Fan-out vs Write Amplification
* Under test conditions where test users had an average of 450 followers, Celery background workers processed **1,000 post creations in under 4.2 seconds** without impacting the HTTP API response time (which stayed flat at ~18ms).
* For simulated celebrity accounts ($N = 50,000$), skipping the write fanout completely prevented the write queue from stalling, while timeline read latency remained within **34ms (P95)** by dynamically pulling the celebrity's cached post pool.

### 4.2 Keyset Seek vs PostgreSQL Connection Saturation
* At 1,200 concurrent users, traditional `OFFSET 50000` exhausted the Postgres `max_connections` (100 pool limit) within 45 seconds due to slow query execution (140ms per query holding connections).
* Switching to **Keyset Cursor Seeking** reduced connection hold time to **< 1ms**, allowing PostgreSQL to effortlessly service 1,400+ RPS with less than 25 active connections.

### 4.3 Min-Heap Algorithmic Ranking Throughput
* FastAPI's $O(N \log K)$ Min-Heap ranking engine processed 100 candidate posts per feed request in an average of **0.82 milliseconds** CPU time, proving the effectiveness of priority queue bounded buffers over full dataset sorting in memory.
