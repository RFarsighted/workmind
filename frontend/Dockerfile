FROM node:22-alpine

WORKDIR /app

RUN npm install --global pnpm@12.6.0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173
CMD ["pnpm", "dev", "--", "--host", "0.0.0.0"]
