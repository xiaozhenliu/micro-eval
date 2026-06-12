import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    // Use jsdom for component rendering tests.
    // Files in __tests__/components/ get jsdom; pure logic tests use node.
    environment: "jsdom",
    globals: false,
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
