FROM ghcr.io/astral-sh/uv:python3.14-alpine as build
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

FROM python:3.14-alpine

WORKDIR /app
COPY --from=build /app/.venv /opt/venv
COPY processor.py .
ENV PATH="/opt/venv/bin:${PATH}"
CMD ["python", "processor.py"]
