import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// vite.config.ts runs in Node but isn't covered by tsconfig.json's "include"
// (scoped to src/ only), so @types/node isn't pulled in here — declare just
// what we use rather than adding a devDependency for one config file.
declare const process: { env: Record<string, string | undefined> }

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  preview: {
    // `vite preview` (used by the Docker image) reads its own proxy config,
    // separate from `server.proxy` above which only applies to `vite dev`.
    // VITE_BACKEND_URL lets docker-compose point this at the `backend`
    // service name; defaults to localhost for a bare `npm run preview`.
    host: true,
    port: 4173,
    proxy: {
      '/api': process.env.VITE_BACKEND_URL || 'http://localhost:8000',
    },
  },
})
