FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG API_UPSTREAM_URL=http://127.0.0.1:8000
ENV API_UPSTREAM_URL=$API_UPSTREAM_URL
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
