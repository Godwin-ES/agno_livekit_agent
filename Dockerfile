FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install uv
RUN uv sync
CMD ["uv", "run", "main.py", "start"]
