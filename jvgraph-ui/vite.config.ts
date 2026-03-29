import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const base = env.VITE_BASE_PATH || '/'
  const prod = mode === 'production'

  return {
    base: base.endsWith('/') ? base : `${base}/`,
    plugins: [react()],
    build: {
      target: 'es2022',
      sourcemap: false,
      minify: 'esbuild',
      cssMinify: true,
      chunkSizeWarningLimit: 600,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            if (
              id.includes('node_modules/react-dom') ||
              id.includes('node_modules/react/')
            ) {
              return 'vendor-react'
            }
            if (id.includes('cytoscape') || id.includes('dagre')) {
              return 'vendor-graph'
            }
            if (id.includes('prism')) {
              return 'vendor-prism'
            }
            if (id.includes('axios')) {
              return 'vendor-axios'
            }
            return undefined
          },
        },
      },
    },
    esbuild: prod
      ? {
          legalComments: 'none',
          drop: ['console', 'debugger'],
        }
      : undefined,
  }
})
