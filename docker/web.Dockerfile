FROM node:22-alpine

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend .
ENV AGENTGATE_API_URL=http://api:8000
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
