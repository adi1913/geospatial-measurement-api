# Stage 1: build the static site. The API URL is baked in at build time (Vite env variables).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_MAX_UPLOAD_MB=20
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_MAX_UPLOAD_MB=$VITE_MAX_UPLOAD_MB
RUN npm run build

# Stage 2: serve the static files with nginx.
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
