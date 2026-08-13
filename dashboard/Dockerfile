# ---- Builder ----
FROM node:24-slim AS builder
ENV PNPM_HOME="/pnpm" PATH="/pnpm:$PATH" NEXT_TELEMETRY_DISABLED=1
RUN npm install -g pnpm@10.6.2

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

# Client-side API base URL is baked in at build time by Next.js.
ARG NEXT_PUBLIC_API_URL=https://sysinfo-api.onrender.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN pnpm build

# ---- Runner ----
FROM node:24-slim AS runner
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
ENV PNPM_HOME="/pnpm" PATH="/pnpm:$PATH"

WORKDIR /app

RUN npm install -g pnpm@10.6.2

COPY --from=builder /app/package.json /app/pnpm-lock.yaml /app/pnpm-workspace.yaml ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/public ./public

EXPOSE 3000

# Render injects PORT; next start reads process.env.PORT automatically.
CMD ["pnpm", "start"]