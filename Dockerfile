FROM python:3.12-slim
WORKDIR /app
# LiveKit's native library needs glib, which the slim image doesn't ship.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
# Dependencies first, so a code-only change rebuilds in seconds.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
CMD ["uv", "run", "--no-sync", "main.py", "start"]
