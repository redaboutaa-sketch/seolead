# Solar site frontend.
#
# Multi-stage, standalone output. The runtime image carries a Next server, the
# traced `node_modules` subset it actually imports, and nothing else — no build
# toolchain, no source, no dev dependencies. On a host running a dozen containers
# with swap already exhausted, that difference is not cosmetic.
#
# The build runs with a placeholder API key. `lib/api.ts` throws without one, and
# a build-time fetch failure would otherwise turn into a silently empty page: this
# way the failure is a build error, and the real key arrives only at runtime.

FROM node:22-alpine AS deps
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY web/ ./
ENV NEXT_TELEMETRY_DISABLED=1
ENV SEOLEAD_INTERNAL_KEY=build-time-placeholder
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3100
ENV HOSTNAME=0.0.0.0

# A dedicated unprivileged user rather than node:node, matching the numeric-uid
# convention the other services in this stack use.
RUN addgroup -g 10003 -S seolead && adduser -u 10003 -S -G seolead seolead

COPY --from=builder --chown=10003:10003 /app/.next/standalone ./
COPY --from=builder --chown=10003:10003 /app/.next/static ./.next/static
COPY --from=builder --chown=10003:10003 /app/public ./public

USER 10003:10003
EXPOSE 3100

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3100/robots.txt').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
