FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /build/.venv && /build/.venv/bin/pip install --no-cache-dir .

FROM python:3.12-slim
ENV PATH="/build/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=builder /build/.venv /build/.venv
RUN mkdir /app && chown 10001:10001 /app
WORKDIR /app
USER 10001:10001
ENTRYPOINT ["quakewatch"]
CMD ["list", "--window", "day"]
