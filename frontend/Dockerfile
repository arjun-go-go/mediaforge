FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL=/api
ARG NEXT_PUBLIC_ALLOW_SELF_SIGNUP=false
ARG BACKEND_URL=http://api:8100
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_ALLOW_SELF_SIGNUP=${NEXT_PUBLIC_ALLOW_SELF_SIGNUP}
ENV BACKEND_URL=${BACKEND_URL}
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_ALLOW_SELF_SIGNUP=false
ENV BACKEND_URL=http://api:8100
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./next.config.js
EXPOSE 3100
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
