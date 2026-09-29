# System Design Decisions & Architectural Rationale (ADR)

> **Project:** ScaleFeed (FeedX)  
> **Author:** ScaleFeed Engineering Team  
> **Scope:** High-Throughput Distributed Social Feed Engine  
> **Status:** Production Architecture

---

## Overview
This document outlines the **20 foundational architectural design decisions (ADRs)** implemented in ScaleFeed. Each decision reflects real-world engineering trade-offs between latency, data consistency, operational complexity, and infrastructure cost.

---

## Table of Contents
1. [PostgreSQL vs MongoDB (Relational vs Document Store)](#1-postgresql-vs-mongodb)
2. [Followers Graph: Relational DB vs Graph Database (Neo4j)](#2-followers-graph-relational-vs-graph-database)
3. [Cursor-Based Pagination vs Offset-Based Pagination](#3-cursor-based-pagination-vs-offset-based-pagination)
4. [Media Handling: S3/Cloudinary CDN vs Database BLOBs](#4-media-handling-s3cloudinary-vs-database-blobs)
5. [Redis vs Memcached for Feed Caching](#5-redis-vs-memcached-for-feed-caching)
6. [Cache Invalidation: Cache-Aside vs Write-Through vs Write-Behind](#6-cache-invalidation-strategy)
7. [Cache Stampede & Thundering Herd Mitigation](#7-cache-stampede-thundering-herd-mitigation)
8. [Redis Memory Management & Eviction Policy](#8-redis-memory-eviction-policy)
9. [Fan-out-on-Write (Push) vs Fan-out-on-Read (Pull)](#9-fan-out-on-write-vs-fan-out-on-read)
10. [The "Celebrity / Hot Key" Problem & Hybrid Fan-out](#10-celebrity-problem--hybrid-fan-out)
11. [Feed Ranking Algorithm & Time-Decay Engagement Scoring](#11-feed-ranking-algorithm)
12. [Redis Data Structures: Sorted Sets (ZSET) vs Lists](#12-redis-sorted-sets-zset-vs-lists)
13. [Real-time Notifications: WebSockets vs SSE vs Long Polling](#13-websockets-vs-sse-vs-long-polling)
14. [Horizontal WebSocket Scaling via Redis Pub/Sub](#14-horizontal-websocket-scaling-via-redis-pubsub)
15. [Event-Driven Decoupling with Celery & Redis Queues](#15-event-driven-decoupling-with-celery)
16. [Asynchronous Task Idempotency & Acknowledgment](#16-task-idempotency--acknowledgment)
17. [API Rate Limiting: Token Bucket Algorithm with Redis](#17-api-rate-limiting-token-bucket)
18. [Authentication Architecture: Dual-Token JWT with Rotation](#18-authentication-dual-token-jwt-with-rotation)
19. [Scaling to 10 Lakh (1M) Daily Active Users](#19-scaling-to-10-lakh-1m-dau)
20. [NGINX Reverse Proxy, Health Checks & Containerization](#20-nginx-reverse-proxy--containerization)

---

### 1. PostgreSQL vs MongoDB
* **Context:** We need to store user credentials, user profiles, posts, likes, comments, and the follower-following graph.
* **Alternatives Considered:** MongoDB (NoSQL Document Store), PostgreSQL (RDBMS).
* **Decision:** Selected **PostgreSQL 16**.
* **Rationale & Trade-offs:**
  * Social connections require strong referential integrity (e.g., when a user deletes their account, cascade deletions or tombstone records must cleanly handle related likes, comments, and follow relations).
  * ACID transactions prevent race conditions on like counters and duplicate follow entries.
  * PostgreSQL provides rich JSONB support for flexible post metadata without sacrificing schema enforcement for relational entities.
  * Postgres provides superior B-Tree and composite indexing capabilities crucial for keyset pagination.

---

### 2. Followers Graph: Relational DB vs Graph Database
* **Context:** Need to represent follower and following relationships and calculate mutual connections.
* **Alternatives Considered:** Neo4j (Graph Database), PostgreSQL Junction Table (`followers` table with `user_id` and `follower_id`).
* **Decision:** Selected **PostgreSQL with Composite B-Tree Indexes**.
* **Rationale & Trade-offs:**
  * Introducing a dedicated graph database like Neo4j at early to mid-scale adds significant DevOps overhead, distributed transaction complexity, and synchronization delays.
  * In PostgreSQL, a junction table `user_follows(follower_id, followed_id)` with composite unique indexes `(follower_id, followed_id)` and reverse index `(followed_id, follower_id)` executes 1st-degree follower lookups in under 1ms.
  * Mutual friend queries are solved efficiently via SQL set intersection (`INTERSECT`). When scaling past 5M users, graph traversal can be migrated to Amazon Neptune or Neo4j.

---

### 3. Cursor-Based Pagination vs Offset-Based Pagination
* **Context:** Need to support continuous mobile/web infinite scroll for thousands of posts per feed.
* **Alternatives Considered:** Offset pagination (`OFFSET 10000 LIMIT 20`), Cursor/Keyset pagination (`WHERE (created_at, id) < (cursor_timestamp, cursor_id) LIMIT 20`).
* **Decision:** Selected **Cursor-Based (Keyset) Pagination**.
* **Rationale & Trade-offs:**
  * **Performance:** Offset pagination incurs $O(N)$ scanning time; the database must scan and discard 10,000 rows before returning row 10,001. Keyset pagination leverages B-Tree indexes to seek directly to the cursor position in $O(\log N)$ time.
  * **Consistency:** If a new post is inserted while a user is scrolling on page 2, offset pagination shifts rows, showing duplicates on page 3. Cursor pagination is deterministic and immune to row shifts.

---

### 4. Media Handling: S3/Cloudinary vs Database BLOBs
* **Context:** Users attach images and videos to feed posts.
* **Alternatives Considered:** Storing binary files directly in PostgreSQL as `BYTEA` / BLOBs vs Cloud Object Storage (AWS S3 / Cloudinary) with CloudFront CDN.
* **Decision:** Selected **Cloud Object Storage (S3/Cloudinary) with CDN Edge Caching**.
* **Rationale & Trade-offs:**
  * Storing binary BLOBs inside Postgres leads to rapid database bloat, degrades buffer pool cache hit ratios, and dramatically slows down backups and replication.
  * Storing media externally allows the database to keep lightweight 64-byte URL strings. Media assets are served directly from global CDN edge caches without touching backend application servers.

---

### 5. Redis vs Memcached for Feed Caching
* **Context:** Generating personalized feeds by joining DB tables on every request creates an unbearable DB load. An in-memory cache is mandatory.
* **Alternatives Considered:** Memcached, Redis.
* **Decision:** Selected **Redis 7**.
* **Rationale & Trade-offs:**
  * Memcached only supports simple Key-Value strings. Redis supports rich data structures, specifically **Sorted Sets (`ZSET`)**, which allow us to store post IDs ordered by timestamps or ranking scores.
  * Redis provides native **Pub/Sub** and Streams, eliminating the need for a separate message bus for real-time WebSocket notifications.
  * Redis supports snapshots (RDB) and append-only files (AOF) for crash recovery.

---

### 6. Cache Invalidation Strategy
* **Context:** When a post is updated or deleted, or when new posts are published, the cache must remain consistent without stale reads.
* **Alternatives Considered:** Write-Through, Write-Behind (Write-Back), Cache-Aside (Lazy Loading).
* **Decision:** Selected **Cache-Aside Pattern with Time-To-Live (TTL)**.
* **Rationale & Trade-offs:**
  * In Cache-Aside, the application first checks Redis. If hit, data is served. If miss, it queries Postgres, populates Redis, and returns the response.
  * Writes invalidate or update specific cache keys. We enforce a default TTL (e.g., 6 hours for active feeds) so dead or inactive user feeds naturally expire without consuming RAM.

---

### 7. Cache Stampede & Thundering Herd Mitigation
* **Context:** When a viral post's cache expires, thousands of concurrent requests might hit the PostgreSQL database simultaneously to regenerate the cache.
* **Alternatives Considered:** No protection, Probabilistic Early Expiration (XFetch), Distributed Mutex Locking (Redis `SETNX`).
* **Decision:** Selected **Distributed Mutex Lock (`SETNX`) with Jittered TTL**.
* **Rationale & Trade-offs:**
  * When a cache miss occurs for a hot key, the worker attempts to acquire an atomic lock in Redis (`SET lock:post_id token EX 5 NX`).
  * Only one worker regenerates the cache from Postgres; all other concurrent requests wait or receive stale data for a few milliseconds, completely shielding the database from collapse.

---

### 8. Redis Memory Eviction Policy
* **Context:** In-memory storage is bounded. When Redis reaches its `maxmemory` threshold, it must discard keys predictably without dropping critical session or rate-limit data.
* **Alternatives Considered:** `noeviction`, `allkeys-lru`, `volatile-lru`, `allkeys-lfu`.
* **Decision:** Selected **`volatile-lru` (Least Recently Used with TTL)**.
* **Rationale & Trade-offs:**
  * Feed caches and temporary query results are created with an explicit TTL (`EXPIRE`).
  * `volatile-lru` guarantees that only transient cached feed items with TTLs are eligible for eviction, leaving persistent keys (like token revocation blacklists or metrics counters) safe.

---

### 9. Fan-out-on-Write vs Fan-out-on-Read
* **Context:** When User A publishes a post, how do User A's followers receive it in their feed?
* **Alternatives Considered:**
  1. *Fan-out-on-Write (Push):* When User A posts, write the post ID into the feed mailbox of all followers immediately.
  2. *Fan-out-on-Read (Pull):* When a follower opens their app, query the database for posts from all accounts they follow.
* **Decision:** Selected **Hybrid Fan-out Architecture**.
* **Rationale & Trade-offs:**
  * Fan-out-on-Write provides ultra-fast read latency ($O(1)$ from Redis), but explodes when a user has millions of followers (5M writes per single post!).
  * Fan-out-on-Read minimizes write load but destroys database read performance on high-frequency feed queries.
  * Therefore, we use a threshold-based Hybrid model (see Decision 10).

---

### 10. The Celebrity Problem & Hybrid Fan-out
* **Context:** High-profile accounts ("Celebrities" with > 25,000 followers) overwhelm write queues if Fan-out-on-Write is used.
* **Alternatives Considered:** Pure push, Pure pull.
* **Decision:** Implemented **Hybrid Fan-out with Celebrity Cutoff ($N = 25,000$)**.
* **Rationale & Trade-offs:**
  * **Standard Users ($< 25k$ followers):** Handled via **Fan-out-on-Write**. When they post, a Celery worker pushes their `post_id` into their followers' Redis `ZSET` feed mailboxes.
  * **Celebrity Users ($\ge 25k$ followers):** Handled via **Fan-out-on-Read**. Their posts are NOT pushed to millions of mailboxes. Instead, when a follower requests their feed, their timeline is fetched from Redis and dynamically merged with recent posts from the celebrities they follow.

---

### 11. Feed Ranking Algorithm
* **Context:** Chronological feeds prioritize noise over quality. We need an algorithmic balance of recency, social proof, and relevance.
* **Alternatives Considered:** Flat chronological order, Complex Deep Learning Ranker (too heavy for initial tier), Decayed Score Formula (Hacker News / Reddit inspired).
* **Decision:** Selected **Decayed Score Formula executed via Min-Heap / Priority Queue**.
* **Algorithm Formula:**
  $$\text{Score} = \frac{\text{Likes} \times 2 + \text{Comments} \times 3 + \text{Shares} \times 5}{(\text{Age in Hours} + 2)^{1.5}}$$
* **Rationale & Trade-offs:**
  * Linear calculation computed in $O(1)$ per post.
  * In the FastAPI ranking service, a Min-Heap of size $K$ (e.g., $K=20$) maintains the top 20 posts in $O(N \log K)$ time without loading thousands of records into memory.

---

### 12. Redis Data Structures: Sorted Sets (ZSET) vs Lists
* **Context:** Storing user feed timelines in Redis.
* **Alternatives Considered:** Redis `LIST` (`LPUSH` / `LRANGE`), Redis `ZSET` (`ZADD` / `ZREVRANGEBYSCORE`).
* **Decision:** Selected **Redis Sorted Sets (`ZSET`)**.
* **Rationale & Trade-offs:**
  * Redis `LIST` supports pagination by index offset, but inserting an out-of-order post or removing a deleted post is an expensive $O(N)$ operation.
  * `ZSET` uses a Skip List + Hash Map internally. Each post has a score (Timestamp or Decayed Ranking Score).
  * Keyset pagination maps directly to `ZREVRANGEBYSCORE feed:user_id (cursor_score -inf LIMIT 0 20`, achieving $O(\log N + M)$ seek performance.
  * Trimming old feed items past 500 posts is trivial: `ZREMRANGEBYRANK feed:user_id 0 -501`.

---

### 13. Real-time Notifications: WebSockets vs SSE vs Long Polling
* **Context:** Users must receive instant alerts when someone likes their post, comments, or follows them.
* **Alternatives Considered:** Short Polling, HTTP Long Polling, Server-Sent Events (SSE), WebSockets.
* **Decision:** Selected **WebSockets**.
* **Rationale & Trade-offs:**
  * Short/Long polling creates immense HTTP connection setup/teardown overhead, consuming TCP sockets and server memory.
  * SSE is uni-directional (Server $\to$ Client). While sufficient for alerts, WebSockets provide bi-directional duplex channels, preparing the infrastructure for instant direct messaging and typing indicators without altering the network protocol.

---

### 14. Horizontal WebSocket Scaling via Redis Pub/Sub
* **Context:** When running multiple instances of the WebSocket gateway behind NGINX, User A might be connected to Server 1 while User B (who likes A's post) is connected to Server 2.
* **Alternatives Considered:** Sticky Sessions (IP Hash), Centralized Broker with Redis Pub/Sub.
* **Decision:** Selected **Redis Pub/Sub Message Broker**.
* **Rationale & Trade-offs:**
  * Sticky sessions fail to solve the cross-server notification delivery problem.
  * With Redis Pub/Sub, each WebSocket node subscribes to a channel format `user:notifications:{user_id}` for its connected clients. When an event occurs anywhere in the cluster, it publishes to Redis, and only the node holding User A's active socket picks it up and pushes it down the wire.

---

### 15. Event-Driven Decoupling with Celery
* **Context:** When a user likes a post, executing DB writes, updating counters, triggering push notifications, and recalculating ranking scores inside the HTTP request cycle causes 300ms+ latency.
* **Alternatives Considered:** Synchronous execution inside Django view, Asynchronous background tasks with Celery + Redis.
* **Decision:** Selected **Celery + Redis Task Queue**.
* **Rationale & Trade-offs:**
  * The HTTP handler validates input, enqueues a `process_post_like.delay(user_id, post_id)` task, and returns `202 Accepted` / `200 OK` in **under 15ms**.
  * Celery workers execute the side-effects asynchronously: database counter increments, cache invalidation, and WebSocket dispatch.

---

### 16. Task Idempotency & Acknowledgment
* **Context:** If a Celery worker restarts while processing an event, the message broker may redeliver the task, potentially double-counting a like or sending duplicate notifications.
* **Alternatives Considered:** Fire-and-forget, Idempotency Keys with Redis.
* **Decision:** Enforced **Idempotency Keys (`SETNX`) & Late Acknowledgment (`acks_late=True`)**.
* **Rationale & Trade-offs:**
  * Every task generates a unique hash based on `(event_type, user_id, target_id, timestamp_window)`.
  * The worker checks Redis before executing: if the key exists, the task is safely discarded.
  * `acks_late=True` ensures tasks are only removed from the queue after successful execution, preventing task loss during worker crashes.

---

### 17. API Rate Limiting: Token Bucket
* **Context:** Prevent brute-force login attacks, spam post creation, and aggressive scraping.
* **Alternatives Considered:** Fixed Window Counter, Sliding Window Log, Token Bucket.
* **Decision:** Implemented **Token Bucket Algorithm via Redis Lua Scripts**.
* **Rationale & Trade-offs:**
  * Fixed window counters suffer from boundary bursts (2x traffic right at the minute boundary).
  * Sliding window log consumes excessive memory by storing timestamps for every request.
  * Token bucket provides smooth rate limiting with burst allowance, implemented atomically in a single Redis Lua round-trip.

---

### 18. Authentication: Dual-Token JWT with Rotation
* **Context:** Secure, stateless API authentication across multiple microservices without hitting the database on every HTTP request.
* **Alternatives Considered:** Session Cookies, Single long-lived JWT, Dual-Token JWT (Short-lived Access + Refresh Token Rotation).
* **Decision:** Selected **Dual-Token Architecture with Refresh Token Rotation**.
* **Rationale & Trade-offs:**
  * **Access Token:** Short lifespan (15 minutes), digitally signed with HMAC-SHA256, verified statelessly by both DRF and FastAPI without database queries.
  * **Refresh Token:** Longer lifespan (7 days), stored in an HTTP-only secure cookie, rotated on every refresh request.
  * Compromised refresh tokens are blacklisted in Redis with an automatic TTL matching the token's remaining validity.

---

### 19. Scaling to 10 Lakh (1M) Daily Active Users
* **Context:** How ScaleFeed handles growth from 10,000 to 1,000,000 DAU without architectural redesign.
* **Scaling Strategy Roadmap:**
  1. **Database Tier:**
     * Introduce PostgreSQL **Primary-Replica (Leader-Follower)** topology. Primary handles writes; 3 read-replicas handle feed queries and profile reads.
     * Horizontal partitioning (Table Sharding) on `posts` and `likes` using hash-sharding on `user_id` (`pg_partman` or Citus).
  2. **Caching Tier:**
     * Migrate from standalone Redis to **Redis Cluster** with 6 nodes (3 masters, 3 replicas) with consistent hashing to prevent memory exhaustion.
  3. **Compute Tier:**
     * NGINX distributes traffic across multiple stateless Gunicorn/Uvicorn workers scaled horizontally on Kubernetes or AWS ECS.

---

### 20. NGINX Reverse Proxy & Containerization
* **Context:** Need unified entry point, SSL termination, path-based microservice routing, and consistent local/production environments.
* **Alternatives Considered:** Direct port exposure, API Gateway (Kong/Traefik), NGINX.
* **Decision:** Selected **NGINX + Docker Compose**.
* **Rationale & Trade-offs:**
  * NGINX routes `/api/v1/feed/rank`, `/api/v1/ai`, and `/ws/` to FastAPI, while routing `/api/v1/auth`, `/api/v1/posts`, and `/admin/` to Django DRF.
  * NGINX handles gzip/brotli compression and SSL termination, relieving Python application processes of network transport overhead.
  * Docker Compose guarantees identical development, testing, and production environments.
