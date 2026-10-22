# Azure Cloud Architecture & Scaling Guide for ScaleFeed

This guide details how to deploy and scale **ScaleFeed** on Microsoft Azure with managed high-availability services, zero-downtime database routing, and KEDA auto-scaling.

---

## 1. Cloud Infrastructure Architecture

```
[ Azure Front Door / CDN ] (Global Edge, SSL, WAF)
            │
            ▼
[ Azure Container Apps (ACA) ]
   ├── scalefeed-drf-core (Write Service, Port 8000)
   ├── scalefeed-fastapi (Read Service & WebSockets, Port 8001)
   └── scalefeed-celery-worker (Autoscaled 1-20 via KEDA)
            │                         │
            ▼                         ▼
[ Azure Cache for Redis ]   [ Azure DB for PostgreSQL ]
 (Clustered Premium P1)      (Flexible Server + PgBouncer on 6432)
                                 ├── Primary (Writes)
                                 └── Read Replica (Reads)
```

---

## 2. Enabling PgBouncer on Azure PostgreSQL Flexible Server

1. Navigate to your **Azure Database for PostgreSQL Flexible Server** resource.
2. In the left sidebar under **Settings**, select **Server Parameters**.
3. Search for `pgbouncer.enabled` and toggle it to `ON`.
4. Update your application's connection port from `5432` to `6432`.
   * **Why:** PgBouncer pools thousands of short-lived client connections down to ~100 persistent server connections, preventing database memory exhaustion under viral traffic.

---

## 3. Configuring Database Read-Replicas in Django

1. In the Azure Portal, select **Replication** under your PostgreSQL Flexible Server and click **Add Replica**.
2. Azure provisions an asynchronous read-replica via WAL streaming replication.
3. Configure your environment variables in Azure Container Apps:
   ```bash
   DATABASE_URL="postgres://admin:pass@scalefeed-pg.postgres.database.azure.com:6432/scalefeed?sslmode=require"
   DATABASE_REPLICA_URL="postgres://admin:pass@scalefeed-pg-replica.postgres.database.azure.com:6432/scalefeed?sslmode=require"
   ```
4. Django's `PrimaryReplicaRouter` (`common.db_router.PrimaryReplicaRouter`) automatically routes:
   * `POST /api/v1/posts/`, `POST /api/v1/users/follow/` $\rightarrow$ Primary DB
   * `GET /api/v1/feed/`, `GET /api/v1/users/{id}/` $\rightarrow$ Read Replica

---

## 4. KEDA Auto-Scaling for Celery Workers

Apply the KEDA manifest (`deploy/azure/keda-celery-scaler.yaml`):
```bash
kubectl apply -f deploy/azure/keda-celery-scaler.yaml
```
* **Trigger:** Monitors the Redis list length of the `celery` queue.
* **Scaling Behavior:**
  * When a viral post creates 50,000 fan-out jobs, KEDA instantly scales worker instances from **1 to 20**.
  * Once the queue empties, KEDA scales instances back down to **1** after a 60-second cooldown, optimizing Azure cloud spend.
