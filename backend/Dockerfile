FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv && useradd --create-home --shell /usr/sbin/nologin aitlas
COPY pyproject.toml uv.lock alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY config ./config
RUN uv sync --frozen --no-dev && chown -R aitlas:aitlas /app
ENV PATH="/app/.venv/bin:${PATH}"
USER aitlas
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
