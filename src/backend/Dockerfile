# NorthCX backend. Build context: src/backend
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml requirements.lock ./
# Every dependency comes from the hash-pinned lock (scripts/lock.sh); the project itself is installed without resolving anything.
RUN pip install --no-cache-dir --prefix=/install --require-hashes -r requirements.lock
COPY northcx ./northcx
RUN pip install --no-cache-dir --prefix=/install --no-deps .

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app PORT=3000
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin northcx
COPY --from=build /install /usr/local
WORKDIR /app
# The bundled example agent, tools and scenarios. Mount your own spec and scenario directories and set
# NORTHCX_REGISTRY, NORTHCX_AGENTS_DIR and NORTHCX_SCENARIOS_DIR to run your own agents.
COPY --chown=northcx examples ./examples
USER northcx
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/ready' % os.environ.get('PORT','3000'), timeout=2)"
CMD ["python", "-m", "northcx"]
