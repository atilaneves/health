#!/bin/sh
# Fetch what isn't cached today, log in if needed, rebuild and open the page. See src/health/run.py.
cd "$(dirname "$0")" && exec uv run --quiet python -m health.run "$@"
