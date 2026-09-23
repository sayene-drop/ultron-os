FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    HOST=0.0.0.0

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root user for security (compatible with Hugging Face Spaces & Render)
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /app/memory/logs && \
    chown -R appuser:appuser /app

# Copy application source code
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 7860 8788 10000

CMD ["python", "server.py"]
