.PHONY: setup build test test-authz test-authn dev release clean sdk-build sdk-publish db

PG_VERSION ?= 16
PG_CONTAINER ?= postkit-test
PG_PORT ?= 5433
DATABASE_URL ?= postgresql://postgres:postgres@localhost:$(PG_PORT)/postgres
PYTEST = cd sdk && uv run --extra dev pytest

GREEN = \033[0;32m
NC = \033[0m

db:
	@nc -z localhost $(PG_PORT) 2>/dev/null || \
		(docker start $(PG_CONTAINER) 2>/dev/null || make setup)

setup:
	@echo "Starting Postgres $(PG_VERSION)..."
	@docker run -d --name $(PG_CONTAINER) \
		-e POSTGRES_PASSWORD=postgres \
		-p $(PG_PORT):5432 \
		postgres:$(PG_VERSION) > /dev/null
	@echo "Waiting for Postgres..."
	@sleep 3
	@until docker exec $(PG_CONTAINER) pg_isready -q; do sleep 1; done
	@echo "$(GREEN)✓ Postgres $(PG_VERSION) ready$(NC)"

build:
	@mkdir -p dist
	@./scripts/build.sh > dist/postkit.sql
	@./scripts/build.sh authz > dist/authz.sql
	@./scripts/build.sh authn > dist/authn.sql
	@echo "$(GREEN) Built dist/postkit.sql, dist/authz.sql, dist/authn.sql$(NC)"

test: db build
ifdef TEST
	@DATABASE_URL=$(DATABASE_URL) $(PYTEST) -v $(TEST)
else
	@DATABASE_URL=$(DATABASE_URL) $(PYTEST) -v
endif

test-authz: db build
	@DATABASE_URL=$(DATABASE_URL) $(PYTEST) -v tests/authz/

test-authn: db build
	@DATABASE_URL=$(DATABASE_URL) $(PYTEST) -v tests/authn/

dev: build test
	@echo "$(GREEN) Build and tests passed$(NC)"

release:
ifndef VERSION
	$(error VERSION is required. Usage: make release VERSION=1.0.0)
endif
	@echo "Releasing v$(VERSION)..."
	@make build
	@make test
	@echo "$(GREEN) Ready to release$(NC)"
	@echo ""
	@echo "Next steps:"
	@echo "  git tag v$(VERSION) && git push --tags"

sdk-build:
	@cd sdk && uv build
	@echo "$(GREEN) Built SDK$(NC)"

sdk-publish: sdk-build
	@cd sdk && uv publish
	@echo "$(GREEN) Published SDK to PyPI$(NC)"

clean:
	@docker rm -f $(PG_CONTAINER) 2>/dev/null || true
	@rm -rf dist/ sdk/dist/ sdk/.venv .venv
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN) Cleaned up$(NC)"
