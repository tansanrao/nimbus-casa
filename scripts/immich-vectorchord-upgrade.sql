-- Rehearsed with Immich 3.3.5, PostgreSQL 16.15, and the pinned image in
-- kubernetes/apps/immich/database/app/cluster.yaml.
-- Stop Immich writers, verify a fresh backup, and take a stopped-database
-- volume snapshot BEFORE changing the image. Run only after the new database
-- is ready. Rolling back after COMMIT requires restoring pre-upgrade data;
-- changing the image alone does not revert extension/index formats.
\set ON_ERROR_STOP on
SET maintenance_work_mem = '256MB';
BEGIN;
ALTER EXTENSION vector UPDATE TO '0.8.6';
ALTER EXTENSION vchord UPDATE TO '1.1.1';
REINDEX INDEX face_index;
REINDEX INDEX clip_index;
COMMIT;
