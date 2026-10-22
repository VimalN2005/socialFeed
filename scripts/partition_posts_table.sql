-- ==============================================================================
-- ScaleFeed: Declarative PostgreSQL Table Partitioning by Range (created_at)
-- Designed for Azure Database for PostgreSQL Flexible Server
-- ==============================================================================
-- Purpose:
-- Prevents B-Tree index bloat and RAM exhaustion as the 'posts' table scales past 10M+ rows.
-- Queries utilizing Keyset Cursor Pagination ('WHERE created_at < cursor LIMIT 20')
-- leverage PostgreSQL Partition Pruning to scan ONLY the current month's partition.
-- ==============================================================================

BEGIN;

-- 1. Create the new partitioned master table
CREATE TABLE IF NOT EXISTS posts_partitioned (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    caption TEXT NOT NULL DEFAULT '',
    media_url VARCHAR(500) NOT NULL DEFAULT '',
    likes_count INTEGER NOT NULL DEFAULT 0,
    comments_count INTEGER NOT NULL DEFAULT 0,
    shares_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- 2. Define Monthly Partitions
CREATE TABLE IF NOT EXISTS posts_y2026m08 PARTITION OF posts_partitioned
    FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS posts_y2026m09 PARTITION OF posts_partitioned
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS posts_y2026m10 PARTITION OF posts_partitioned
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS posts_y2026m11 PARTITION OF posts_partitioned
    FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS posts_y2026m12 PARTITION OF posts_partitioned
    FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

-- 3. Catch-all Default Partition for out-of-range records
CREATE TABLE IF NOT EXISTS posts_default PARTITION OF posts_partitioned DEFAULT;

-- 4. Recreate High-Performance Composite Indexes on the Partitioned Table
-- (PostgreSQL automatically propagates these indexes to all child partitions)
CREATE INDEX IF NOT EXISTS idx_posts_user_created ON posts_partitioned (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_created_at_desc ON posts_partitioned (created_at DESC);

-- 5. Copy Existing Unpartitioned Data into the Partitioned Structure (if migrating)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'posts') THEN
        INSERT INTO posts_partitioned (id, user_id, caption, media_url, likes_count, comments_count, shares_count, created_at, updated_at)
        SELECT id, user_id, caption, media_url, likes_count, comments_count, shares_count, created_at, updated_at
        FROM posts
        ON CONFLICT (id, created_at) DO NOTHING;
    END IF;
END $$;

COMMIT;

-- Verification Query to Confirm Partition Pruning:
-- EXPLAIN (ANALYZE, BUFFERS) 
-- SELECT * FROM posts_partitioned 
-- WHERE created_at < NOW() 
-- ORDER BY created_at DESC 
-- LIMIT 20;
