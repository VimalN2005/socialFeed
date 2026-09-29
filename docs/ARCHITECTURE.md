# System Architecture & Technical Specifications

> **Project:** ScaleFeed (FeedX)  
> **Document:** High-Level Design (HLD) & Low-Level Design (LLD)

---

## 1. High-Level Design (HLD)

ScaleFeed is built using a modern decoupled micro-service architecture designed for high read throughput, asynchronous event decoupling, and real-time duplex communication.

```mermaid
flowchart TD
    Client["Client Devices<br/>(Web / Mobile Apps)"]

    subgraph Edge ["Edge Layer"]
        NGINX["NGINX Reverse Proxy / Load Balancer<br/>Port 80 / 443"]
    end

    subgraph AppLayer ["Application Services"]
        DRF["Django REST Framework<br/>(Auth, Social Graph, Posts CRUD, Permissions)<br/>Port 8000"]
        FastAPI["FastAPI Engine<br/>(Feed Ranking, AI Hashtags, WebSockets)<br/>Port 8001"]
        CeleryWorker["Celery Background Workers<br/>(Fan-out Pipeline, Async Notifications, Counters)"]
    end

    subgraph DataLayer ["Data & Caching Tier"]
        Postgres[("PostgreSQL 16 Primary DB<br/>Users, Posts, Followers, Likes")]
        RedisCache[("Redis 7 Cache & ZSET<br/>Feed Timelines, Rate Limits")]
        RedisBroker[("Redis 7 Message Broker<br/>Celery Queue & Pub/Sub")]
        S3Storage[("AWS S3 / Cloudinary CDN<br/>Images, Media Blobs")]
    end

    Client -->|HTTP / REST & WebSocket| NGINX
    NGINX -->|/api/v1/auth, /api/v1/posts| DRF
    NGINX -->|/api/v1/feed, /api/v1/ai, /ws/| FastAPI

    DRF --> Postgres
    DRF --> S3Storage
    DRF -->|Enqueue Events| RedisBroker
    
    FastAPI --> RedisCache
    FastAPI -->|Pub/Sub Listen| RedisBroker
    FastAPI --> Postgres

    RedisBroker --> CeleryWorker
    CeleryWorker --> Postgres
    CeleryWorker --> RedisCache
    CeleryWorker -->|Publish Notification| RedisBroker
```

---

## 2. Database ER Diagram (LLD)

The data model enforces relational integrity with composite indexes tailored for keyset pagination and social graph lookups.

```mermaid
erDiagram
    USER ||--o{ POST : creates
    USER ||--o{ LIKE : gives
    USER ||--o{ COMMENT : writes
    USER ||--o{ FOLLOW : follows
    USER ||--o{ FOLLOW : followed_by
    POST ||--o{ LIKE : receives
    POST ||--o{ COMMENT : has

    USER {
        uuid id PK "Primary Key (UUID v4)"
        string username UK "Unique, Indexed"
        string email UK "Unique, Indexed"
        string password_hash
        string bio
        string avatar_url
        int followers_count "Denormalized for O(1) checks"
        int following_count "Denormalized for O(1) checks"
        boolean is_celebrity "True if followers >= 25,000"
        datetime created_at
    }

    POST {
        uuid id PK "Primary Key (UUID v4)"
        uuid user_id FK "Indexed with created_at"
        text caption
        string media_url
        int likes_count "Denormalized counter"
        int comments_count "Denormalized counter"
        float ranking_score "Precomputed score"
        datetime created_at "Composite index (user_id, created_at DESC)"
        datetime updated_at
    }

    FOLLOW {
        uuid id PK
        uuid follower_id FK "Composite UK (follower_id, followed_id)"
        uuid followed_id FK "Index (followed_id, created_at DESC)"
        datetime created_at
    }

    LIKE {
        uuid id PK
        uuid user_id FK "Composite UK (user_id, post_id)"
        uuid post_id FK "Index (post_id)"
        datetime created_at
    }

    COMMENT {
        uuid id PK
        uuid post_id FK "Index (post_id, created_at ASC)"
        uuid user_id FK
        text content
        datetime created_at
    }
```

---

## 3. Event-Driven Sequence Diagrams

### 3.1 Post Creation & Hybrid Fan-out Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Creator as User / Creator
    participant Gateway as NGINX
    participant CoreAPI as Django DRF
    participant DB as PostgreSQL
    participant Broker as Redis Queue
    participant Worker as Celery Worker
    participant Cache as Redis ZSET Feed

    Creator->>Gateway: POST /api/v1/posts/ (Caption, Media)
    Gateway->>CoreAPI: Forward Request
    CoreAPI->>DB: INSERT into posts
    CoreAPI->>Broker: Enqueue FanoutTask(post_id, user_id, is_celebrity)
    CoreAPI-->>Creator: 201 Created (Instant Response < 25ms)

    alt Standard User (Followers < 25,000)
        Worker->>Broker: Dequeue FanoutTask
        Worker->>DB: Fetch Follower IDs (Batch of 1,000)
        loop For Each Follower
            Worker->>Cache: ZADD feed:follower_id score=timestamp post_id
            Worker->>Cache: ZREMRANGEBYRANK feed:follower_id 0 -501 (Cap at 500)
        end
    else Celebrity Account (Followers >= 25,000)
        Worker->>Broker: Dequeue FanoutTask
        Note over Worker,Cache: Skip Push Fanout! Post will be dynamically pulled at read time.
    end
```

### 3.2 Real-time Like & Instant WebSocket Notification

```mermaid
sequenceDiagram
    autonumber
    actor Liker as User B
    participant CoreAPI as Django DRF
    participant Broker as Redis Message Bus
    participant Worker as Celery Worker
    participant FastWS as FastAPI WebSocket Node
    actor Author as User A (Post Author)

    Liker->>CoreAPI: POST /api/v1/posts/{id}/like/
    CoreAPI->>Broker: Enqueue ProcessLikeTask(liker_id, post_id)
    CoreAPI-->>Liker: 200 OK (Liked)

    Worker->>Broker: Pick up Task
    Worker->>Worker: Check Idempotency Key (Redis SETNX)
    Worker->>DB: Update like counter (+1)
    Worker->>Broker: PUBLISH channel="user:notifications:UserA" payload="User B liked your post"
    Broker->>FastWS: Message delivered via Redis Pub/Sub
    FastWS->>Author: Push JSON via active WebSocket Connection (< 10ms)
```

---

## 4. DSA & Algorithmic Complexity in ScaleFeed

| Feature | Data Structure / Algorithm | Time Complexity | Space Complexity | Why it matters |
|---|---|---|---|---|
| **Feed Ranking** | **Min-Heap (Priority Queue)** | $O(N \log K)$ | $O(K)$ | Dynamically ranks top $K$ posts across millions without sorting entire datasets in memory. |
| **Cursor Pagination** | **B-Tree Seek (Keyset Seek)** | $O(\log N + M)$ | $O(1)$ | Eliminates $O(N)$ scan penalties of `OFFSET`, guarantees deterministic infinite scroll without duplicates. |
| **Mutual Friends** | **Adjacency Set Intersection** | $O(\min(|A|, |B|))$ | $O(|A| + |B|)$ | Computes shared social connections rapidly using SQL/in-memory set intersection. |
| **Timeline Trimming** | **Skip List (Redis ZSET)** | $O(\log N + M)$ | $O(N)$ | Keeps active feed sizes bounded (top 500 posts per user) with automatic rank trimming (`ZREMRANGEBYRANK`). |
| **Rate Limiter** | **Token Bucket (Redis Lua)** | $O(1)$ | $O(1)$ | Prevents brute force and API abuse atomically with zero race conditions. |
