import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const localProxyTarget = 'http://localhost:8000'
const renderProxyTarget = 'https://gold-intelligence-backend.onrender.com'
const proxyTarget = process.env.VITE_DEV_PROXY_TARGET ||
  (process.env.RENDER === 'true' ? renderProxyTarget : localProxyTarget)

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: [
      'gold-intelligence-0jlq.onrender.com',
    ],
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        secure: true,
      },
    },
  },
})
