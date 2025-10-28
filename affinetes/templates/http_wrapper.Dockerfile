# Two-stage build Dockerfile for injecting HTTP server
# This is used when the base image doesn't have an HTTP server

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Switch to root to install dependencies
USER root

# Install HTTP server dependencies
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx pydantic

# Create rayfine directory and copy server
RUN mkdir -p /app/_rayfine
COPY http_server.py /app/_rayfine/server.py
RUN echo "" > /app/_rayfine/__init__.py

# Make directory world-writable to avoid permission issues
RUN chmod -R 777 /app/_rayfine

# Expose HTTP port
EXPOSE 8000

# Start server with 4 workers for high concurrency
WORKDIR /app
CMD ["python", "-m", "uvicorn", "_rayfine.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]