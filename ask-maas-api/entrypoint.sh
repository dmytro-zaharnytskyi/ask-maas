#!/bin/bash
# Entrypoint script for Ask MaaS orchestrator

# Activate the Python environment
export PATH=/home/askmaas/.local/bin:$PATH
export PYTHONPATH=/app:/home/askmaas/.local/lib/python3.11/site-packages

# Debug: Show what's available
echo "Python path: $(which python)"
echo "Checking for uvicorn..."
python -c "import uvicorn; print('Uvicorn found:', uvicorn.__version__)" || echo "Uvicorn not found in Python"

# Try different ways to start uvicorn
if [ -f /home/askmaas/.local/bin/uvicorn ]; then
    echo "Starting with local uvicorn binary"
    exec /home/askmaas/.local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
else
    echo "Starting with python -m uvicorn"
    exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
fi

