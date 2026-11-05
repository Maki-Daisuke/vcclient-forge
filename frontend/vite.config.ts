import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  base: './',
  // Keep the Python-served legacy UI in dist until the native controls work.
  build: { outDir: 'preview-dist' },
});
