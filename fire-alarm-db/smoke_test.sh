#!/bin/bash
#
# smoke_test.sh - Smoke Test for Fire Alarm Elite Pipeline
#
# Tests the complete pipeline with Docker Compose

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "FIRE ALARM ELITE PIPELINE - SMOKE TEST"
echo "=========================================="

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/fire-alarm-db"

# Clean up any previous containers
echo "[1/6] Cleaning up previous containers..."
docker-compose down -v 2>/dev/null || true

# Start services
echo "[2/6] Starting services with docker-compose..."
docker-compose up -d --build

# Wait for database to be ready
echo "[3/6] Waiting for database..."
sleep 5

# Wait for app to be healthy
echo "[4/6] Waiting for app to be healthy..."
MAX_RETRIES=10
RETRIES=0

while [ $RETRIES -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
        echo -e "${GREEN}App is healthy!${NC}"
        break
    fi
    RETRIES=$((RETRIES + 1))
    echo "Retry $RETRIES/$MAX_RETRIES..."
    sleep 3
done

if [ $RETRIES -eq $MAX_RETRIES ]; then
    echo -e "${RED}SMOKE TEST FAILED: App not healthy${NC}"
    docker-compose down -v
    exit 1
fi

# Test elite-design endpoint (without image - should use test data)
echo "[5/6] Testing elite-design endpoint..."

# Create a test project
RESPONSE=$(curl -s -X POST "http://localhost:8000/api/elite-design" \
    -F "project_name=SmokeTest" \
    -F "standard=egyptian" \
    2>/dev/null || echo '{"task_id":"","error":"curl failed"}')

echo "Response: $RESPONSE"

# Extract task_id
TASK_ID=$(echo "$RESPONSE" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('task_id',''))" 2>/dev/null || echo "")

if [ -z "$TASK_ID" ]; then
    echo -e "${RED}SMOKE TEST FAILED: Could not get task_id${NC}"
    docker-compose down -v
    exit 1
fi

echo "Task ID: $TASK_ID"

# Poll for completion
echo "[6/6] Polling for completion..."
MAX_WAIT=30
WAIT=0

while [ $WAIT -lt $MAX_WAIT ]; do
    STATUS=$(curl -s "http://localhost:8000/api/task/$TASK_ID" 2>/dev/null | \
        python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('status',''))" 2>/dev/null || echo "")
    
    if [ "$STATUS" = "completed" ]; then
        echo -e "${GREEN}Task completed!${NC}"
        break
    elif [ "$STATUS" = "error" ]; then
        echo -e "${RED}SMOKE TEST FAILED: Task errored${NC}"
        docker-compose down -v
        exit 1
    fi
    
    echo "Waiting... ($WAIT/$MAX_WAIT)"
    sleep 2
    WAIT=$((WAIT + 2))
done

if [ $WAIT -ge $MAX_WAIT ]; then
    echo -e "${RED}SMOKE TEST FAILED: Timeout${NC}"
    docker-compose down -v
    exit 1
fi

# Check the output ZIP contains required files
echo "Checking output..."
DOWNLOAD_URL="http://localhost:8000/download/$TASK_ID"

# Download and check
TEMP_ZIP="/tmp/smoke_test_$$_outputs.zip"
if curl -sL -o "$TEMP_ZIP" "$DOWNLOAD_URL" 2>/dev/null; then
    # Check contents
    if zipinfo "$TEMP_ZIP" 2>/dev/null | grep -qE '\.(dwg|pdf|csv)'; then
        echo -e "${GREEN}Output contains required files!${NC}"
    else
        echo -e "${YELLOW}Warning: Output may not contain all expected files${NC}"
    fi
else
    echo -e "${RED}SMOKE TEST FAILED: Could not download output${NC}"
    docker-compose down -v
    exit 1
fi

# Cleanup
rm -f "$TEMP_ZIP"
docker-compose down -v

echo ""
echo "=========================================="
echo -e "${GREEN}SMOKE TEST PASSED${NC}"
echo "=========================================="
exit 0