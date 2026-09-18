import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端页面的"接线图"：
// 1. 页面在 5173 端口打开；
// 2. 页面上凡是发给 /api 开头的请求，自动转交给后端的 8000 端口，
//    这样浏览器就不会因为"端口不同"而拦截我们的请求。
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
