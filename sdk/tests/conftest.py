"""Shared pytest configuration for postkit SDK tests."""

import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/postgres"
)
