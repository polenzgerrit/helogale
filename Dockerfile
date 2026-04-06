FROM python:3.14-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wireless-tools \
    iw \
    curl \
    iproute2 \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

# Create app directory
WORKDIR /app

# Copy project files
COPY pyproject.toml poetry.lock* ./
COPY README.md ./
COPY src/ ./src/
COPY dashboard.html ./

# Install Python dependencies
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# Create a non-root user for running the app (but we'll still run as root for raw sockets)
RUN useradd -m -d /home/helogale helogale || true

# Expose ports
EXPOSE 8080 8765

# Create entrypoint script
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run as root to allow raw socket access
USER root

ENTRYPOINT ["/entrypoint.sh"]
