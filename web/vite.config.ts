import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/api/": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        headers: { Origin: "http://127.0.0.1:8766" },
        timeout: 300000,
        proxyTimeout: 300000,
      },
    },
    watch: {
      // SUMO exports and Blender outputs can be installed while this viewer runs.
      // Watch source code; serve large immutable data files on the next reload.
      ignored: ["**/public/replays/**", "**/public/assets/**"],
    },
  },
});
