#!/usr/bin/env node
/**
 * Generate a CycloneDX 1.5 SBOM for a Node skill from its package-lock.json.
 *
 * Usage: node scripts/gen-node-sbom.mjs <skill-dir> [<skill-dir> ...]
 *   If no args, scans skills/* for package-lock.json and emits sbom.cyclonedx.json
 *   in each.
 *
 * The SBOM is derived strictly from the resolved lockfile (lockfileVersion 3),
 * so it reflects exactly what `npm ci` would install — no network required.
 */

import { readFileSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";

const ALG_MAP = { sha512: "SHA-512", sha256: "SHA-256", sha1: "SHA-1", md5: "MD5" };

function nameFromKey(key) {
  // key examples: "", "node_modules/foo", "node_modules/@scope/foo",
  // "node_modules/a/node_modules/@scope/bar"
  const seg = key.split("node_modules/").pop();
  return seg || null;
}

function purl(name, version) {
  const encoded = name.replace(/^@/, "%40");
  return `pkg:npm/${encoded}@${version}`;
}

function componentFromEntry(name, entry) {
  const version = entry.version;
  const comp = {
    type: "library",
    name,
    version,
    purl: purl(name, version),
  };
  if (entry.dev) comp.scope = "optional"; // dev-only dependency
  if (entry.integrity) {
    const [alg, hash] = entry.integrity.split("-", 2);
    const algo = ALG_MAP[alg];
    if (algo && hash) {
      comp.hashes = [{ alg: algo, content: hash }];
    }
  }
  if (entry.resolved) comp.externalReferences = [{ type: "distribution", url: entry.resolved }];
  return comp;
}

function buildBom(skillDir) {
  const lockPath = join(skillDir, "package-lock.json");
  const pkgPath = join(skillDir, "package.json");
  if (!existsSync(lockPath)) return null;

  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  const pkg = existsSync(pkgPath) ? JSON.parse(readFileSync(pkgPath, "utf8")) : {};
  const lockVersion = lock.lockfileVersion;

  const components = [];
  const packages = lock.packages || {};
  for (const [key, entry] of Object.entries(packages)) {
    if (key === "") continue; // root
    const name = nameFromKey(key);
    if (!name || !entry.version) continue;
    components.push(componentFromEntry(name, entry));
  }

  const rootName = pkg.name || skillDir.split("/").pop();
  const rootVersion = pkg.version || "0.0.0";

  const bom = {
    bomFormat: "CycloneDX",
    specVersion: "1.5",
    version: 1,
    metadata: {
      timestamp: new Date().toISOString(),
      component: {
        type: "application",
        name: rootName,
        version: rootVersion,
        description: pkg.description || `Node skill: ${rootName}`,
      },
      properties: [
        { name: "sbom:generator", value: "gen-node-sbom.mjs" },
        { name: "sbom:source", value: `package-lock.json (lockfileVersion ${lockVersion})` },
      ],
    },
    components,
  };
  return bom;
}

function main() {
  let dirs = process.argv.slice(2);
  if (dirs.length === 0) {
    const root = resolve(".");
    const skillsRoot = join(root, "skills");
    if (existsSync(skillsRoot)) {
      dirs = [];
      for (const name of readdirSync(skillsRoot)) {
        const p = join(skillsRoot, name);
        if (existsSync(join(p, "package-lock.json"))) dirs.push(p);
      }
    }
  }
  if (dirs.length === 0) {
    console.error("No skills with package-lock.json found.");
    process.exit(1);
  }
  for (const dir of dirs) {
    const bom = buildBom(dir);
    if (!bom) {
      console.error(`skip (no package-lock.json): ${dir}`);
      continue;
    }
    const out = join(dir, "sbom.cyclonedx.json");
    writeFileSync(out, JSON.stringify(bom, null, 2) + "\n");
    console.log(`wrote ${out} (${bom.components.length} components)`);
  }
}

try {
  main();
} catch (e) {
  console.error(e);
  process.exit(1);
}
