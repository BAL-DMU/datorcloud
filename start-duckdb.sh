#!/bin/bash

# Install necessary tools
apt-get update && apt-get install -y socat net-tools lsof

# Kill any existing processes using port 4213
kill $(lsof -t -i:4213) 2>/dev/null || true

# Start DuckDB with UI
echo "Starting DuckDB with UI..."
duckdb -ui &
DUCKDB_PID=$!

# Wait for DuckDB to start and bind to the port
echo "Waiting for DuckDB UI to start on port 4213..."
for i in {1..10}; do
  if netstat -tuln | grep -q ':4213'; then
    echo "DuckDB UI is running on port 4213"
    break
  fi
  sleep 1
  if [ $i -eq 10 ]; then
    echo "Timed out waiting for DuckDB UI to start"
    exit 1
  fi
done

# Set up port forwarding with detailed logging
echo "Setting up port forwarding with socat..."
socat -d -d TCP-LISTEN:4213,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:4213 &
SOCAT_PID=$!

# Verify the port forwarding
echo "Verifying port forwarding..."
netstat -tuln | grep 4213

echo "DuckDB UI should now be accessible at http://localhost:4213"
echo "DuckDB PID: $DUCKDB_PID, Socat PID: $SOCAT_PID"

# Keep container running
tail -f /dev/null

# #!/bin/bash
# # Start DuckDB with UI enabled (basic version)
# duckdb -ui &
# # Keep container running
# tail -f /dev/null


# #!/bin/bash
# # Start DuckDB with UI enabled on all interfaces
# duckdb -ui --listen 0.0.0.0:4213 &
# # Keep container running
# tail -f /dev/null
# cat start-duckdb.sh