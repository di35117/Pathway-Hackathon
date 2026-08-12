FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build toolchain, removed in the same layer so it never lands in the image.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ curl && \
    rm -rf /var/lib/apt/lists/*

# Requirements first: this layer stays cached across application code edits.
COPY requirements-slim.txt .
RUN pip install --no-cache-dir -r requirements-slim.txt

# Application code
COPY main.py demo_controller.py pipeline_v2.py ./
COPY core/ core/
COPY pipeline/ pipeline/
COPY dashboard/ dashboard/
COPY sim/ sim/
COPY decision_engine/ decision_engine/
# V2 engine — the default risk and decision path.
COPY risk_engine_v2/ risk_engine_v2/
COPY decision_engine_v2/ decision_engine_v2/
COPY simulation_v2/ simulation_v2/
# The SOP is the single source of truth for temperature ranges; the image is
# not functional without it.
COPY watched_docs/ watched_docs/
COPY scripts/ scripts/

# Durable telemetry lives here so it can be backed by a mounted volume.
RUN mkdir -p metrics dashboard/data

# Fail the build if the SOP did not make it in, rather than falling back to
# hardcoded ranges silently at runtime.
RUN python -c "\
from core.sop_parser import get_product_temp_ranges, get_source; \
assert get_source() == 'sop', 'SOP not readable inside image'; \
n = len(get_product_temp_ranges()); \
assert n == 9, f'expected 9 SOP products, got {n}'; \
print(f'SOP OK: {n} product ranges')"

EXPOSE 5050 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5050/health || exit 1

COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
