// Created by Redfox using Claude
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'AI Command Centre',
        short_name: 'Command Centre',
        description: 'Centro pessoal de IA: conversas, sessões, projectos e modelos locais.',
        lang: 'pt-PT',
        theme_color: '#0e111a',
        background_color: '#0e111a',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      // A API nunca é guardada em cache: só a casca da aplicação.
      workbox: { navigateFallbackDenylist: [/^\/api\//], runtimeCaching: [] },
    }),
  ],
  server: { proxy: { '/api': 'http://127.0.0.1:3000' } },
})
