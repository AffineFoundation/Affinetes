ARG BASE_IMAGE
FROM ${BASE_IMAGE}

RUN apt-get update && apt-get install -y \
    gcc cmake build-essential \
    g++ libffi-dev \
    git \
    curl \
    wget \
    patch \
    bash \
    unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --recurse-submodules https://github.com/angosr/AgentGym.git AgentGym \
    && cd AgentGym \
    && git checkout 81d8c5fc7ddca4b3c929264ee7bf3791c867b085 \
    && git submodule update --init --recursive

ENV PATH=/opt/miniconda/envs/agentenv/bin:/opt/miniconda/bin:$PATH

ARG ENV_NAME
ENV ENV_NAME=${ENV_NAME}

COPY preprocess_env.sh /app/
RUN chmod +x /app/preprocess_env.sh && /app/preprocess_env.sh

RUN pip install /app/AgentGym/agentenv

COPY postprocess_env.sh /app/
RUN chmod +x /app/postprocess_env.sh && /app/postprocess_env.sh

ENV ALFWORLD_DATA=/root/.cache/alfworld

ARG TOOL_NAME
ENV TOOL_NAME=${TOOL_NAME}
COPY env.py /app/

# Add health check to detect and restart hung containers or OOM conditions
# Interval: Check every 60s (reduced frequency to avoid overhead)
# Timeout: Wait max 10s for response
# Start period: Grace period of 60s after container starts
# Retries: Mark unhealthy after 2 consecutive failures (120s total)
# Check 1: HTTP health endpoint must respond
# Check 2: Memory usage must be < 90% of container limit (for cgroup v2)
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=2 \
    CMD sh -c 'curl -f http://localhost:8000/health || exit 1; \
        MEM_CURRENT=$(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo 0); \
        MEM_MAX=$(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo max); \
        if [ "$MEM_MAX" != "max" ]; then \
            MEM_USAGE_PCT=$((MEM_CURRENT * 100 / MEM_MAX)); \
            [ $MEM_USAGE_PCT -lt 90 ] || exit 1; \
        fi'

WORKDIR /sandbox
# IMPORTANT: Must use single worker mode (no --workers or --workers 1)
# Reason: AgentGym evaluator creates stateful agents that callback to the same server
# Multiple workers would cause requests to be routed to different processes, losing state
# For better performance within single process, use asyncio event loop
CMD ["uvicorn", "env:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app", "--loop", "asyncio", "--workers", "1"]