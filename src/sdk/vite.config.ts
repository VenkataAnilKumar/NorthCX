import { defineConfig } from "vite";

// Two files: an ES module for apps that bundle it, and one self-contained script that registers <northcx-chat> for a plain <script> tag.
export default defineConfig({
  build: {
    outDir: "dist", emptyOutDir: false, minify: true, sourcemap: false, target: "es2020",
    lib: { entry: "src/index.ts", name: "NorthCX", formats: ["es", "iife"], fileName: (format) => (format === "es" ? "northcx-client.js" : "northcx-widget.js") },
  },
});
