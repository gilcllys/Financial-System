# Stage 1: Build
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npx ng build

# Stage 2: Nginx
FROM nginx:alpine

COPY --from=build /app/dist/financial-system-ui/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 4200

CMD ["nginx", "-g", "daemon off;"]
