FROM python:3.13-slim AS builder

WORKDIR /app

COPY examples/notes/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

COPY sdk /sdk
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /sdk


FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --chown=appuser:appuser examples/notes/app ./app

USER appuser

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "4", "--access-logfile", "-", "app:create_app()"]
