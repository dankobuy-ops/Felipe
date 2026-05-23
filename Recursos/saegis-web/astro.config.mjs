import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  base: '/Apps/segurosaegis',
  outDir: '../docs/segurosaegis',
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
  },
});
