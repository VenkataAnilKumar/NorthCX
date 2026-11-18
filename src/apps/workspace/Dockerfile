# NorthCX Workspace (the staff app). Build context: src  (the workspace root: Workspace uses the shared packages in ../../packages)
# NORTHCX_API_URL is where the console's server reaches the backend. Next.js bakes the proxy rule in at build time,
# so rebuild the image if the backend address changes.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/workspace/package.json apps/workspace/
COPY packages/ui/package.json packages/ui/
COPY packages/api-client/package.json packages/api-client/
RUN npm ci
COPY apps/workspace apps/workspace
COPY packages packages
ARG NORTHCX_API_URL=http://backend:3000
ENV NORTHCX_API_URL=$NORTHCX_API_URL NEXT_TELEMETRY_DISABLED=1
# Build only this app: the image holds just this app and the shared packages, so the root build (both apps) cannot run here.
RUN npm run build -w @northcx/workspace

FROM node:22-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3002 HOSTNAME=0.0.0.0
WORKDIR /app
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin northcx
COPY --from=build --chown=northcx /app/apps/workspace/.next/standalone ./
COPY --from=build --chown=northcx /app/apps/workspace/.next/static ./apps/workspace/.next/static
USER northcx
EXPOSE 3002
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT+'/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/workspace/server.js"]
