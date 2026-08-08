# Multi-stage: build React UI, then run FastAPI serving API + static files.
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin API when served from FastAPI.
ENV VITE_API_ORIGIN=
RUN npm run build && test -f dist/index.html && ls -la dist && ls -la dist/assets

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
# Explicit destination (avoid clobber / ignore quirks with nested dist names).
RUN mkdir -p /app/backend/static
COPY --from=frontend /fe/dist/index.html /app/backend/static/index.html
COPY --from=frontend /fe/dist/assets /app/backend/static/assets
RUN test -f /app/backend/static/index.html \
    && test -d /app/backend/static/assets \
    && ls -la /app/backend/static \
    && ls -la /app/backend/static/assets

WORKDIR /app/backend
ENV STATIC_DIR=/app/backend/static
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
