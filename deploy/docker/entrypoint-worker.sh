#!/bin/sh
set -e

echo "Starting FireAI Celery Worker..."
echo "Worker ID: $(hostname)"
echo "Mode: ${WORKER_MODE:-default}"
echo "Broker: ${FIREAI_CELERY_BROKER:-redis://localhost:6379/0}"

# V143 Phase 0-A: Replaced time.sleep(10) stub with real Celery worker.
# The worker connects to Redis broker and processes tasks from the analysis queue.
# Reference: NFPA 72-2022 §10.6 (audit trail), §14.2.4 (correlation ID)

WORKER_LOGLEVEL="${CELERY_LOGLEVEL:-info}"
WORKER_CONCURRENCY="${CELERY_CONCURRENCY:-2}"
WORKER_QUEUES="${CELERY_QUEUES:-analysis,default}"

exec celery -A backend.worker.celery_app:celery_app worker \
    --loglevel="${WORKER_LOGLEVEL}" \
    --concurrency="${WORKER_CONCURRENCY}" \
    --queues="${WORKER_QUEUES}" \
    --hostname="fireai-worker@$(hostname)" \
    --without-heartbeat \
    --without-mingle \
    --without-gossip
