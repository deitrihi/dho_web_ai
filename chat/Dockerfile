# DHO 챗봇 프론트엔드 배포용 Dockerfile (Next.js standalone 빌드, NAS docker-compose에서 사용)
FROM node:24-alpine AS base

FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# nginx가 서브패스(예: /chat)로 프록시할 때 씀 — basePath는 빌드 타임에 번들에 박히므로
# 빌드 인자로 받는다 (docker-compose.yml build.args 참고)
ARG NEXT_BASE_PATH=""
ENV NEXT_BASE_PATH=$NEXT_BASE_PATH
RUN npm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# /data/logs(chat_logs named volume 마운트 지점)를 nextjs 소유로 미리 만들어둔다. 없으면
# Docker가 볼륨을 처음 만들 때 root:root로 생성해서, 아래 USER nextjs(비root)가 로그
# 파일을 못 쓰고 EACCES로 실패한다.
RUN mkdir -p /data/logs && chown -R nextjs:nodejs /data/logs

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
