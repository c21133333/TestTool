import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

function resolveVendorChunk(id: string) {
  if (!id.includes('node_modules')) {
    return undefined;
  }

  const normalizedId = id.replace(/\\/g, '/');
  const packagePath = normalizedId.split('node_modules/')[1];
  if (!packagePath) {
    return 'vendor';
  }

  const packageName = packagePath.startsWith('@')
    ? packagePath.split('/').slice(0, 2).join('/')
    : packagePath.split('/')[0];

  if (packageName === 'react' || packageName === 'react-dom' || packageName === 'scheduler') {
    return 'react-vendor';
  }
  if (packageName === 'react-router' || packageName === 'react-router-dom') {
    return 'router';
  }
  if (packageName === '@ant-design/icons') {
    return 'antd-icons';
  }

  return undefined;
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: resolveVendorChunk,
      },
    },
  },
});
