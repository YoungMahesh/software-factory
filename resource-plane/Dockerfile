# Base image with pnpm, openssl, and build utilities
FROM node:20-alpine AS base
RUN apk add --no-cache libc6-compat openssl
RUN corepack enable && corepack prepare pnpm@10.31.0 --activate
WORKDIR /app

# Dependencies stage
FROM base AS deps
WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/theme/package.json ./packages/theme/package.json
COPY packages/types/package.json ./packages/types/package.json

RUN pnpm install --frozen-lockfile

# Development stage (used for containerized local dev)
FROM base AS dev
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /app/packages/theme/node_modules ./packages/theme/node_modules
COPY --from=deps /app/packages/types/node_modules ./packages/types/node_modules
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]

# Builder stage
FROM base AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /app/packages/theme/node_modules ./packages/theme/node_modules
COPY --from=deps /app/packages/types/node_modules ./packages/types/node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN pnpm --filter @repo/web build

# Production runner stage
FROM node:20-alpine AS runner
RUN apk add --no-cache libc6-compat openssl docker-cli curl

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Copy standalone Next.js server bundle and static assets
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/drizzle ./apps/web/drizzle
COPY --from=builder /app/apps/web/drizzle ./drizzle

# Create persistent data directory
RUN mkdir -p /app/.data

EXPOSE 3000

CMD ["node", "apps/web/server.js"]
