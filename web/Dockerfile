FROM node:22-alpine AS deps
WORKDIR /app

COPY web/package*.json ./web/
RUN cd web && npm ci

FROM node:22-alpine AS builder
WORKDIR /app

COPY --from=deps /app/web/node_modules ./web/node_modules
COPY web ./web

# Bake the public API URL into the client bundle at build time.
# This must be an ARG (not ENV) so Next.js webpack can inline it.
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

WORKDIR /app/web
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

COPY --from=builder /app/web/.next ./web/.next
COPY --from=builder /app/web/package*.json ./web/
COPY --from=builder /app/web/public ./web/public
COPY --from=builder /app/web/node_modules ./web/node_modules

EXPOSE 3000

CMD ["npm", "run", "start", "--prefix", "web"]
