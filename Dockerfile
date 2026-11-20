# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY --chown=app:app backend/ ./backend/
COPY --from=frontend --chown=app:app /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/backend/.cache && chown -R app:app /app

USER app
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers '--forwarded-allow-ips=*'"]
