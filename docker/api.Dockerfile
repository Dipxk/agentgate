FROM python:3.12-slim

WORKDIR /app
COPY backend /app/backend
COPY evaluation /app/evaluation
COPY .agentgate /app/.agentgate
RUN pip install --no-cache-dir "/app/backend[postgres]"
ENV AGENTGATE_ROOT=/app
EXPOSE 8000
CMD ["agentgate", "serve", "--host", "0.0.0.0", "--port", "8000"]
