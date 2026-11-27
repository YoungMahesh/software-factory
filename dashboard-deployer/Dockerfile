FROM node:20-alpine AS base
RUN apk add --no-cache libc6-compat openssl
RUN corepack enable && corepack prepare pnpm@10.31.0 --activate
WORKDIR /app

FROM base AS builder
WORKDIR /app
COPY . .

ARG NEXT_PUBLIC_DASHBOARD_COMMIT=""
ENV NEXT_PUBLIC_DASHBOARD_COMMIT=${NEXT_PUBLIC_DASHBOARD_COMMIT}
ENV NEXT_TELEMETRY_DISABLED=1
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; else pnpm install; fi
ENV NODE_ENV=production
RUN pnpm build
RUN mkdir -p /app/public

FROM node:20-alpine AS runner
RUN apk add --no-cache libc6-compat openssl curl
WORKDIR /app

ARG NEXT_PUBLIC_DASHBOARD_COMMIT=""
ENV NEXT_PUBLIC_DASHBOARD_COMMIT=${NEXT_PUBLIC_DASHBOARD_COMMIT}
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
