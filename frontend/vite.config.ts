import { defineConfig, loadEnv } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VCCLIENT_');
  const target = env.VCCLIENT_BACKEND_URL || 'http://127.0.0.1:18888';
  const proxy = {
    '/api': { target, changeOrigin: true },
    '/model_dir': { target, changeOrigin: true },
    '/output.wav': { target, changeOrigin: true },
  };
  return {
    plugins: [svelte()],
    base: './',
    server: { proxy },
    preview: { proxy },
    // Keep the Python-served legacy UI in dist until the native controls work.
    build: { outDir: 'preview-dist' },
  };
});
