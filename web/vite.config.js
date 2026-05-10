import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
var __dirname = dirname(fileURLToPath(import.meta.url));
// In dev, the Vite server proxies /api → http://localhost:8000 so we
// don't have to deal with CORS in the frontend code. In prod, the
// FastAPI server itself serves the built bundle from `jobapply/web_dist`.
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": resolve(__dirname, "src"),
        },
    },
    build: {
        outDir: resolve(__dirname, "../jobapply/web_dist"),
        emptyOutDir: true,
        sourcemap: false,
    },
    server: {
        port: 5173,
        strictPort: false,
        proxy: {
            "/api": {
                target: "http://localhost:8000",
                changeOrigin: true,
            },
        },
    },
});
