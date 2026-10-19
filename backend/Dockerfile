FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/backend

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir ".[keyvault]"

COPY backend/ ./
COPY design/sample-data.json /srv/design/sample-data.json

ENV SAMPLE_DATA_PATH=/srv/design/sample-data.json
EXPOSE 8000
# Apply migrations, then serve the City MCP Gateway.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
