# NorthCX Studio (the operator console). Build context: src  (the workspace root: Studio uses the shared packages in ../../packages)
# NORTHCX_API_URL is where the console's server reaches the backend. Next.js bakes the proxy rule in at build time,
# so rebuild the image if the backend address changes.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/studio/package.json apps/studio/
COPY packages/ui/package.json packages/ui/
COPY packages/api-client/package.json packages/api-client/
RUN npm ci
COPY apps/studio apps/studio
COPY packages packages
ARG NORTHCX_API_URL=http://backend:3000
ENV NORTHCX_API_URL=$NORTHCX_API_URL NEXT_TELEMETRY_DISABLED=1
# Build only this app: the image holds just this app and the shared packages, so the root build (both apps) cannot run here.
RUN npm run build -w @northcx/studio

FROM node:22-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3001 HOSTNAME=0.0.0.0
WORKDIR /app
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin northcx
COPY --from=build --chown=northcx /app/apps/studio/.next/standalone ./
COPY --from=build --chown=northcx /app/apps/studio/.next/static ./apps/studio/.next/static
USER northcx
EXPOSE 3001
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT+'/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/studio/server.js"]
