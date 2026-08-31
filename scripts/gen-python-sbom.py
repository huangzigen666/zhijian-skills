#!/usr/bin/env python3
"""
Generate a CycloneDX 1.5 SBOM for the Python surface of zhijian-skills.

Unlike the Node skills (which ship package-lock.json), the Python scripts are
not packaged, so there is no lockfile to read. Instead we statically scan
every .py file, classify imports as stdlib / local / third-party, and emit a
SBOM of the discovered third-party distributions with their pin status.

Usage: python3 scripts/gen-python-sbom.py
Output: sbom.python.cyclonedx.json (repo root)
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root
SKILLS = ROOT / "skills"

# import-name -> distribution-name (only the non-obvious ones)
ALIAS = {
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "PIL": "pillow",
    "dateutil": "python-dateutil",
    "lxml": "lxml",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "np": "numpy",
    "pd": "pandas",
}

# Known pin status. wcx is pinned to a git commit (see upstream-trust docs);
# the others are currently unpinned in the repo.
WCX_COMMIT = "37cf4d5fd6a0677c2137601292f6942ff731d4b9"
PINNED = {"wcx": f"git commit {WCX_COMMIT} (github.com/lovstudio/wcx)"}
UNPINNED_NOTE = "no version pin found in repo; add to requirements and pin a version"


def collect_local_modules() -> set[str]:
    stems: set[str] = set()
    for p in SKILLS.rglob("*.py"):
        stems.add(p.stem)
    return stems


def scan_imports(local: set[str]) -> dict[str, set[str]]:
    stdlib = set(sys.stdlib_module_names)
    third: dict[str, set[str]] = {}
    for skill in sorted(SKILLS.iterdir()):
        if not skill.is_dir():
            continue
        for f in sorted(skill.rglob("*.py")):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            for node in ast.walk(tree):
                name = None
                if isinstance(node, ast.Import):
                    name = node.names[0].name.split(".")[0]
                elif isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        continue
                    if node.module:
                        name = node.module.split(".")[0]
                if not name:
                    continue
                if name in stdlib or name in local:
                    continue
                dist = ALIAS.get(name, name)
                third.setdefault(dist, set()).add(skill.name)
    return third


def build_bom(third: dict[str, set[str]]) -> dict:
    components = []
    for dist in sorted(third):
        if dist in PINNED:
            version = WCX_COMMIT
            pin = PINNED[dist]
        else:
            version = "unpinned"
            pin = UNPINNED_NOTE
        comp = {
            "type": "library",
            "name": dist,
            "version": version,
            "purl": f"pkg:pypi/{dist}",
            "scope": "required",
            "properties": [
                {"name": "sbom:used-by", "value": ", ".join(sorted(third[dist]))},
                {"name": "sbom:pin-status", "value": pin},
            ],
        }
        components.append(comp)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "component": {
                "type": "application",
                "name": "zhijian-skills",
                "version": "unpinned",
                "description": "Agent skill portfolio (Python surface)",
            },
            "properties": [
                {"name": "sbom:generator", "value": "gen-python-sbom.py"},
                {"name": "sbom:method", "value": "AST import scan (no lockfile available)"},
            ],
        },
        "components": components,
    }


def main() -> int:
    local = collect_local_modules()
    third = scan_imports(local)
    bom = build_bom(third)
    out = ROOT / "sbom.python.cyclonedx.json"
    out.write_text(json.dumps(bom, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(bom['components'])} components)")
    for c in bom["components"]:
        status = "pinned" if c["version"] != "unpinned" else "UNPINNED"
        print(f"  - {c['name']} [{status}] used by {c['properties'][0]['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
