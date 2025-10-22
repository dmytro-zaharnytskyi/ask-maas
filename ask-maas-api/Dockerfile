# Multi-stage build for Ask MaaS Orchestrator API
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1001 -s /bin/bash askmaas

# Set working directory
WORKDIR /app

# Copy Python packages from builder (with proper ownership)
COPY --from=builder --chown=askmaas:askmaas /root/.local /home/askmaas/.local

# Copy application code
COPY --chown=askmaas:askmaas . .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set Python path
ENV PATH=/home/askmaas/.local/bin:$PATH \
    PYTHONPATH=/app:/home/askmaas/.local/lib/python3.11/site-packages \
    PYTHONUNBUFFERED=1

# Switch to non-root user
USER askmaas

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
