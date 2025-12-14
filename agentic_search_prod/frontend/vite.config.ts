import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/static/',  // Set base path for production deployment
  server: {
    port: 5173,
    proxy: {
      '/search': 'http://localhost:8023',
      '/tools': 'http://localhost:8023',
      '/models': 'http://localhost:8023',
      '/auth': 'http://localhost:8023',
    }
  },
  build: {
    outDir: '../backend/static',  // Build directly into backend/static folder
    emptyOutDir: true,
    sourcemap: true,
  }
})
