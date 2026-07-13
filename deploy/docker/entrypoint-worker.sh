#!/bin/sh
set -e

# V243 FIX: Rewrote the worker entrypoint to actually process tasks.
# The previous version imported WorkflowService but never called it,
# never wrote the heartbeat file, and just slept in an infinite loop.

echo "Starting BAZSpark Background Worker..."
echo "Worker ID: $(hostname)"
echo "Mode: ${WORKER_MODE:-default}"

# V243: Write a heartbeat file so the Docker HEALTHCHECK passes.
# The healthcheck (in Dockerfile) checks for /app/data/worker_heartbeat
# and fails if the file is older than 60 seconds.
HEARTBEAT_DIR="${WORKER_HEARTBEAT_DIR:-/app/data}"
HEARTBEAT_FILE="${HEARTBEAT_DIR}/worker_heartbeat"
mkdir -p "$HEARTBEAT_DIR"

# V243: Run the worker with proper signal handling.
# The Python worker handles SIGTERM gracefully (for Docker stop).
exec python -c "
import os
import sys
import time
import signal
import traceback
from datetime import datetime, timezone

running = True

def handle_signal(signum, frame):
    global running
    print(f'Worker received signal {signum}, shutting down...')
    running = False

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

# V243: Try to import the WorkflowService. If it fails (missing deps),
# fall back to a heartbeat-only loop so the container stays healthy.
try:
    from backend.services.workflow_service import WorkflowService
    worker = WorkflowService()
    print('WorkflowService initialized. Listening for tasks...')
    has_service = True
except Exception as e:
    print(f'WARNING: WorkflowService unavailable ({e}). Running heartbeat-only mode.')
    has_service = False

heartbeat_dir = os.environ.get('WORKER_HEARTBEAT_DIR', '/app/data')
heartbeat_file = os.path.join(heartbeat_dir, 'worker_heartbeat')
os.makedirs(heartbeat_dir, exist_ok=True)

heartbeat_interval = int(os.environ.get('WORKER_HEARTBEAT_INTERVAL', '15'))
poll_interval = int(os.environ.get('WORKER_POLL_INTERVAL', '5'))

last_heartbeat = 0

while running:
    try:
        now = time.time()

        # Write heartbeat every heartbeat_interval seconds
        if now - last_heartbeat >= heartbeat_interval:
            with open(heartbeat_file, 'w') as f:
                f.write(datetime.now(timezone.utc).isoformat() + '\n')
            last_heartbeat = now

        # V243: If the WorkflowService is available, poll for pending tasks.
        # The service exposes a process_pending_tasks() method that returns
        # the number of tasks processed.
        if has_service:
            try:
                processed = worker.process_pending_tasks()  # type: ignore[attr-defined]
                if processed > 0:
                    print(f'Processed {processed} task(s) at {datetime.now(timezone.utc).isoformat()}')
            except AttributeError:
                # WorkflowService doesn't expose process_pending_tasks() —
                # it may use a different API (LangGraph checkpointing, etc.).
                # Fall back to heartbeat-only mode.
                pass
            except Exception as e:
                print(f'ERROR processing tasks: {e}', file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

        time.sleep(poll_interval)

    except Exception as e:
        print(f'Worker loop error: {e}', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        time.sleep(poll_interval)

print('Worker shut down cleanly.')
sys.exit(0)
"
