import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built to ui/dist and served BY THE GO GATEWAY (see cmd/gateway/main.go spaHandler).
// Node is a build-time dependency only: at demo time no dev server runs, so nothing competes
// with the model for the memory envelope the thesis is about.
//
// base: './' keeps asset URLs relative, so the bundle works no matter what path the gateway
// mounts it at.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    // `npm run dev` only. Proxies the API to the gateway so the dev server is same-origin too,
    // which keeps the fetch code identical between dev and the built bundle.
    proxy: {
      '/ask': 'http://localhost:8080',
      '/products': 'http://localhost:8080',
      '/stats': 'http://localhost:8080',
    },
  },
})
