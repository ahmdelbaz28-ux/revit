#!/bin/sh
set -e

echo "Starting FireAI Background Worker..."
echo "Worker ID: $(hostname)"
echo "Mode: ${WORKER_MODE:-default}"

exec python -c "
import time, os, sys
from backend.services.workflow_service import WorkflowService

def run_worker():
    print('Worker initialized. Listening for tasks...')
    while True:
        try:
            time.sleep(10)
        except KeyboardInterrupt:
            print('Worker shutting down...')
            sys.exit(0)

if __name__ == '__main__':
    run_worker()
"
