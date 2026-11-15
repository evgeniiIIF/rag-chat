FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
RUN printf "%s\n"   "server {"   "  listen 80;"   "  root /usr/share/nginx/html;"   "  index index.html;"   "  location / { try_files \$uri /index.html; }"   "}" > /etc/nginx/conf.d/default.conf
EXPOSE 80
