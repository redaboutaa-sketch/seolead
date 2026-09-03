import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./", import.meta.url)) },
  },
  // Components are rendered with react-dom/server in a few tests; the App
  // Router's JSX has no `import React`, so the automatic runtime is required.
  esbuild: { jsx: "automatic" },
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
});
