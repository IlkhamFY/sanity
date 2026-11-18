import { createReadStream, statSync, cpSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const brandDir = join(here, "../brand");
const brandFiles = [
  "mark-dark.svg",
  "mark-light.svg",
  "logo-dark.svg",
  "logo-light.svg",
  "favicon.svg",
];

function copyBrand(outDir) {
  const dest = join(outDir, "brand");
  mkdirSync(dest, { recursive: true });
  for (const name of brandFiles) {
    cpSync(join(brandDir, name), join(dest, name));
  }
}

export default defineConfig({
  base: "./",
  build: {
    rollupOptions: {
      input: {
        main: resolve(here, "index.html"),
        demo: resolve(here, "demo.html"),
      },
    },
  },
  server: { host: "0.0.0.0", port: 4317, strictPort: true },
  preview: { host: "0.0.0.0", port: 4317, strictPort: true },
  plugins: [
    {
      name: "brand-assets",
      configureServer(server) {
        server.middlewares.use("/brand", (req, res, next) => {
          const name = decodeURIComponent((req.url || "/").split("?")[0].replace(/^\//, ""));
          if (!brandFiles.includes(name)) return next();
          const file = join(brandDir, name);
          try {
            statSync(file);
          } catch {
            return next();
          }
          res.setHeader("Content-Type", "image/svg+xml");
          createReadStream(file).pipe(res);
        });
      },
      closeBundle() {
        copyBrand(join(here, "dist"));
      },
    },
  ],
});
