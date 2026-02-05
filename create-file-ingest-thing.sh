#!/bin/bash
# Command to create a file ingestion thing and upload test data
# This thing parses CSV files with timestamp in column 0

set -e

# 1. Publish the thing creation message
echo "Creating file ingestion thing..."
cat test-file-ingest-thing.json | docker-compose exec -T mqtt-broker mosquitto_pub -h localhost -p 1883 -u mqtt -P mqtt -t frontend_thing_update -s -q 2

# Wait for thing setup
echo "Waiting for thing to be set up (5 seconds)..."
sleep 5

# Check worker logs
echo "Checking worker logs..."
docker-compose logs --tail=10 worker-thing-setup 2>&1 | grep -E "(✓|✗|SUCCESS|FAIL)" || echo "No status markers found in recent logs"

# 2. Upload test data via MinIO mc CLI
echo ""
echo "Uploading test-data.csv to bucket..."
docker run --rm --network=tsm-orchestration_default \
  -v $(pwd)/test-data.csv:/test-data.csv \
  --entrypoint sh minio/mc -c \
  "mc alias set local http://object-storage:9000 minioadmin minioadmin && \
   mc cp /test-data.csv local/file-ingest-thing-bucket/test-data.csv"

echo ""
echo "File ingestion thing created and test data uploaded!"
echo "Check worker-file-ingest logs with: docker-compose logs --tail=20 worker-file-ingest"
