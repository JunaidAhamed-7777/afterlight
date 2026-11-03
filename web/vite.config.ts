import { defineConfig } from "vite";

export default defineConfig({
  server: {
    watch: {
      // SUMO exports and Blender outputs can be installed while this viewer runs.
      // Watch source code; serve large immutable data files on the next reload.
      ignored: ["**/public/replays/**", "**/public/assets/**"],
    },
  },
});
