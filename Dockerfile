# Build stage
FROM ghcr.io/astral-sh/uv:0.5-python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Install project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Install Playwright browsers (cached but also persisted for next stage)
RUN --mount=type=cache,target=/root/.cache/ms-playwright \
    .venv/bin/playwright install --with-deps chromium && \
    cp -r /root/.cache/ms-playwright /root/.ms-playwright

# Production stage
FROM python:3.12-slim-bookworm
WORKDIR /app

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /root/.ms-playwright /root/.cache/ms-playwright
COPY --from=builder /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH"

# Create data and logs directories
RUN mkdir -p /app/data /app/logs

# Default: Bot mode (long-running)
# Override with: CMD ["python", "-m", "tw_homedog", "cli", "run"]
CMD ["python", "-m", "tw_homedog"]
