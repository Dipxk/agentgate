FROM node:22-bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend /app/backend
COPY evaluation /app/evaluation
COPY .agentgate /app/.agentgate
COPY docker/start.sh /app/start.sh
RUN pip3 install --break-system-packages /app/backend \
  && chmod +x /app/start.sh

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend .
ENV AGENTGATE_API_URL=http://127.0.0.1:8000
ENV AGENTGATE_ROOT=/app
RUN npm run build

WORKDIR /app
EXPOSE 3000
CMD ["/app/start.sh"]
