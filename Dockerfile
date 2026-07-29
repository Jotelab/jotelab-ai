# Engine HTTP service (DEVELOPMENT_PLAN §1.1). Deploy target: Render (see README).
# Build: docker build -t jotelab-engine .
# Run:   docker run -p 8000:8000 -e ENGINE_API_KEY=dev-secret jotelab-engine
FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching. requirements.txt pins SymPy + FastAPI/uvicorn.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the packages the service imports (engine, harness, templates, service).
COPY engine ./engine
COPY harness ./harness
COPY templates ./templates
COPY service ./service

EXPOSE 8000

# ENGINE_API_KEY must be provided at runtime; the service fails closed without it.
# $PORT is honored so PaaS hosts (Render/Railway/Fly) can inject their port.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn service.app:app --host 0.0.0.0 --port ${PORT}"]
