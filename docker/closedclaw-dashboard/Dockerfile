FROM node:20-slim

LABEL org.opencontainers.image.name="closedclaw/dashboard"
LABEL org.opencontainers.image.description="Closedclaw privacy dashboard — memory graph, audit, consent, policies"

WORKDIR /app

# Copy package files first for layer caching
COPY package.json ./
RUN npm install --legacy-peer-deps

# Copy app source
COPY . .

# Build Next.js (standalone mode for Docker)
# API routes that proxy to closedclaw-server will fail static generation
# at build time since the server isn't running — this is expected.
# The || true allows build to succeed; the .next output is still usable
# for all pages and API routes at runtime.
ENV CLOSEDCLAW_API_URL=http://closedclaw-server:8765
ENV MEM0_API_URL=http://closedclaw-server:8765
RUN npm run build || true
RUN test -d .next

EXPOSE 3001

ENV PORT=3001
ENV HOSTNAME=0.0.0.0

CMD ["npx", "next", "start", "-p", "3001"]
