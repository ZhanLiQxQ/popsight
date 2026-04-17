import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', '');
  const rawAppUrl = env.APP_URL?.trim();
  const proxyTarget =
    rawAppUrl && rawAppUrl !== 'null' && rawAppUrl !== 'undefined'
      ? rawAppUrl
      : 'http://localhost:8000';

  return {
    plugins: [react(), tailwindcss()],
    define: {
      'process.env.APP_URL': JSON.stringify(proxyTarget),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modifyâfile watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
    },
  };
});
