FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build
FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node","server.js"]
