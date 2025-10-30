# Two-stage build Dockerfile for injecting HTTP server
# This is used when the base image doesn't have an HTTP server

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Switch to root to install dependencies
USER root

# Install HTTP server dependencies
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx pydantic

# Create affinetes directory and copy server
RUN mkdir -p /app/_affinetes
COPY http_server.py /app/_affinetes/server.py
RUN echo "" > /app/_affinetes/__init__.py

# Make directory world-writable to avoid permission issues
RUN chmod -R 777 /app/_affinetes

# Expose HTTP port
EXPOSE 8000

# Start server with 4 workers for high concurrency
WORKDIR /app
CMD ["python", "-m", "uvicorn", "_affinetes.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]