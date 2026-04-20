# Build stage: install deps and build frontend
FROM docker.io/oven/bun:alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./frontend/
RUN cd frontend && bun install
COPY frontend/ ./frontend/
RUN cd frontend && bun run build

# Runtime: Python serves API + static frontend
FROM python:3.12-alpine
RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn[standard]==0.34.2 pydantic==2.11.3 sqlalchemy[asyncio]==2.0.41 aiosqlite==0.21.0
WORKDIR /app/backend
COPY backend/ .
COPY --from=builder /app/frontend/dist/ /app/frontend/dist/
EXPOSE 8000
VOLUME ["/app/backend/kakka.db"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]