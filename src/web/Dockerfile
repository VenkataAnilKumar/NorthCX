# NorthCX web console. Build context: src/web
# NORTHCX_API_URL is where the console's server reaches the backend. Next.js bakes the proxy rule in at build time,
# so rebuild the image if the backend address changes.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NORTHCX_API_URL=http://backend:3000
ENV NORTHCX_API_URL=$NORTHCX_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3001 HOSTNAME=0.0.0.0
WORKDIR /app
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin northcx
COPY --from=build --chown=northcx /app/.next/standalone ./
COPY --from=build --chown=northcx /app/.next/static ./.next/static
USER northcx
EXPOSE 3001
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT+'/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
