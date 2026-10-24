FROM node:24.22.1-trixie-slim

WORKDIR /app
RUN npm install --global npm@12.2.1 \
    && chown node:node /app
USER node

COPY --chown=node:node package.json package-lock.json ./
RUN npm ci
COPY --chown=node:node . ./

ENV API_PROXY_TARGET=http://api:8000 \
    WEB_HOST=0.0.0.0

EXPOSE 5173
CMD ["npm", "run", "dev"]
