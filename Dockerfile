# IA Account Scanner — single Node service (Vite React SPA + Hono API).
FROM node:22-slim

WORKDIR /app

# Install deps first for layer caching.
COPY package.json package-lock.json* ./
RUN npm install

# Build the SPA and typecheck the server.
COPY . .
RUN npm run build

# Persist the 24h scans cache on a writable path.
ENV SCAN_CACHE_DIR=/app/.data
RUN mkdir -p /app/.data

ENV PORT=10000
EXPOSE 10000

CMD ["npm", "start"]
