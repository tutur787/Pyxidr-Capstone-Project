# vite preview needs the full node_modules (vite is a devDependency, and
# `vite preview` is explicitly not a hardened production server — see
# https://vitejs.dev/guide/cli.html#vite-preview) so there's no slimmer
# "production" stage to split out; this mirrors `npm run build && npm run preview`.
FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 4173

CMD ["npm", "run", "preview", "--", "--host"]
