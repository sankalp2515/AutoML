# Development image — source is volume-mounted for hot reload
FROM node:20-alpine

WORKDIR /app

# Install dependencies first (cached layer)
COPY package*.json ./
# npm ci requires package-lock.json; use npm install on first build,
# then the lock file is generated inside the container's node_modules layer.
RUN npm install --legacy-peer-deps

# Expose Next.js dev server port
EXPOSE 3000

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=development

# Source code is mounted via docker-compose volume
# so we don't COPY it here — keeps rebuild fast
CMD ["npm", "run", "dev"]
