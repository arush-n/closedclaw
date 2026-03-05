#!/usr/bin/env node
/**
 * Build script for the Openclaw browser extension.
 *
 * Bundles TypeScript into Chrome-loadable JS and copies static assets
 * into a self-contained `dist/` directory ready for chrome://extensions.
 */

import * as esbuild from "esbuild";
import { cpSync, mkdirSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const dist = resolve(__dirname, "dist");

// Ensure dist dirs exist
mkdirSync(resolve(dist, "background"), { recursive: true });
mkdirSync(resolve(dist, "content_scripts"), { recursive: true });
mkdirSync(resolve(dist, "popup"), { recursive: true });
mkdirSync(resolve(dist, "icons"), { recursive: true });

// Bundle TypeScript entry points
await esbuild.build({
  entryPoints: {
    "background/service_worker": resolve(__dirname, "background/service_worker.ts"),
    "content_scripts/interceptor": resolve(__dirname, "content_scripts/interceptor.ts"),
    "popup/popup": resolve(__dirname, "popup/popup.ts"),
  },
  bundle: true,
  outdir: dist,
  format: "esm",
  target: "es2022",
  sourcemap: true,
  minify: process.argv.includes("--minify"),
});

// Copy static assets
cpSync(resolve(__dirname, "manifest.json"), resolve(dist, "manifest.json"));
cpSync(resolve(__dirname, "popup/popup.html"), resolve(dist, "popup/popup.html"));

// Copy icons if they exist
const iconsDir = resolve(__dirname, "icons");
if (existsSync(iconsDir)) {
  cpSync(iconsDir, resolve(dist, "icons"), { recursive: true });
} else {
  // Generate placeholder SVG icons
  const svgIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" rx="16" fill="#1a1a2e"/><text x="64" y="80" text-anchor="middle" font-family="Arial" font-size="64" font-weight="bold" fill="#e94560">C</text></svg>`;
  const { writeFileSync } = await import("fs");
  for (const size of [16, 48, 128]) {
    writeFileSync(resolve(dist, `icons/icon${size}.png`), svgIcon);
  }
}

console.log("Extension built successfully → dist/");
console.log("Load in Chrome: chrome://extensions → Load unpacked → select dist/");
