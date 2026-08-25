.PHONY: build-beta build-prod build-prod-release install \
        sandbox-up sandbox-rebuild sandbox-down sandbox-build sandbox-shell test clean

# --- Host-native: building/installing the real colette binary ---
# colette itself must run natively on this host for its actual day-to-day
# operation (see ~/.claude/CLAUDE.md) — these targets are not containerized.
build-beta:
	./scripts/build.sh

build-prod:
	./scripts/build.sh prod

build-prod-release:
	./scripts/build.sh prod --bump

install:
	./scripts/install.sh

# --- Docker-only: sandbox lifecycle and testing ---
# Colette's own dev/test workflow always goes through sandbox/ — never run
# pytest or a dev-loop build directly on the host.
#
# Plain `up -d` (no --build): only builds images that don't exist yet, never
# forces a rebuild of already-built ones — apt-get layers aren't perfectly
# reproducible, so `--build` here would recreate (and re-race the
# entrypoint's setup on) every single invocation. Use sandbox-rebuild
# explicitly after changing a Dockerfile.
sandbox-up:
	docker compose -f sandbox/docker-compose.yml up -d
	@for i in $$(seq 1 30); do \
		docker compose -f sandbox/docker-compose.yml exec sandbox test -f /tmp/.sandbox-ready 2>/dev/null && exit 0; \
		sleep 1; \
	done; \
	echo "sandbox container did not become ready in time" >&2; exit 1

sandbox-rebuild:
	docker compose -f sandbox/docker-compose.yml up -d --build
	@for i in $$(seq 1 30); do \
		docker compose -f sandbox/docker-compose.yml exec sandbox test -f /tmp/.sandbox-ready 2>/dev/null && exit 0; \
		sleep 1; \
	done; \
	echo "sandbox container did not become ready in time" >&2; exit 1

sandbox-down:
	docker compose -f sandbox/docker-compose.yml down

sandbox-build: sandbox-up
	docker compose -f sandbox/docker-compose.yml exec sandbox bash -lc \
		'cd /workspace && ./scripts/build.sh && ./scripts/build.sh prod && ./scripts/install.sh'

sandbox-shell: sandbox-up
	docker compose -f sandbox/docker-compose.yml exec sandbox bash

test: sandbox-up
	docker compose -f sandbox/docker-compose.yml exec sandbox python3 -m pytest tests/ -v

clean:
	rm -rf build/
