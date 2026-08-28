import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const serviceProxy = {
  '/live/api': proxy('http://api:8080', '/live/api'),
  '/live/mcp': proxy('http://mcp-server:8081', '/live/mcp'),
  '/live/guardian': proxy('http://guardian:8082', '/live/guardian'),
  '/live/bank': proxy('http://bank-demo:8090', '/live/bank'),
  '/live/gst': proxy('http://gst-portal:8091', '/live/gst'),
  '/live/erp': proxy('http://buyer-erp:8092', '/live/erp'),
  '/live/registry': proxy('http://business-registry:8093', '/live/registry'),
  '/live/funder': proxy('http://funder-marketplace:8094', '/live/funder'),
  '/live/delivery': proxy('http://delivery-demo:8095', '/live/delivery'),
  '/live/ledger': proxy('http://ledger-payment:8096', '/live/ledger'),
}

function proxy(target, prefix) {
  return {
    target,
    changeOrigin: true,
    rewrite: (path) => path.replace(new RegExp(`^${prefix}`), ''),
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 4173,
    proxy: serviceProxy,
  },
  preview: {
    allowedHosts: true,
    proxy: serviceProxy,
  },
})
