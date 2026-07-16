"""Generate and verify the locked runtime dependency license manifest."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections import deque
from importlib.metadata import PackageMetadata, PackageNotFoundError, distribution
from pathlib import Path

PROJECT_DISTRIBUTION = "public-sector-research-mcp"
DEFAULT_OUTPUT = Path("docs/supply-chain/dependency-licenses.json")
LOCK_FILE = Path("uv.lock")
CONDITIONAL_LICENSES = {
    "colorama": ("BSD-3-Clause", "reviewed PyPI metadata"),
    "greenlet": ("MIT AND PSF-2.0", "reviewed PyPI metadata"),
    "pywin32": ("PSF-2.0 AND bundled license files", "reviewed PyPI metadata"),
    "tzdata": ("Apache-2.0", "reviewed PyPI metadata"),
}


def build_manifest() -> dict[str, object]:
    locked = tomllib.loads(LOCK_FILE.read_text())
    packages = {_canonical(item["name"]): item for item in locked["package"]}
    queue: deque[str] = deque([PROJECT_DISTRIBUTION])
    processed: set[str] = set()
    records: dict[str, dict[str, str]] = {}
    while queue:
        requested_name = queue.popleft()
        key = _canonical(requested_name)
        if key in processed:
            continue
        processed.add(key)
        locked_package = packages[key]
        if key != _canonical(PROJECT_DISTRIBUTION):
            try:
                package = distribution(requested_name)
                if package.version != locked_package["version"]:
                    raise RuntimeError(f"installed {key} does not match uv.lock")
                license_name, license_source = _license(package.metadata)
            except PackageNotFoundError:
                license_name, license_source = CONDITIONAL_LICENSES.get(key, ("UNKNOWN", "missing"))
            records[key] = {
                "name": locked_package["name"],
                "version": locked_package["version"],
                "license": license_name,
                "license_source": license_source,
            }
        for dependency in locked_package.get("dependencies", []):
            queue.append(dependency["name"])
    return {
        "schema_version": "1.0",
        "project": PROJECT_DISTRIBUTION,
        "scope": "cross-platform runtime dependency closure from uv.lock",
        "packages": [records[key] for key in sorted(records)],
    }


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _license(metadata: PackageMetadata) -> tuple[str, str]:
    expression = metadata.get("License-Expression")
    if expression:
        return expression.strip(), "License-Expression"
    legacy = metadata.get("License")
    if legacy and "\n" not in legacy and len(legacy) <= 200:
        return legacy.strip(), "License"
    classifiers = [
        value.removeprefix("License :: ")
        for value in metadata.get_all("Classifier", [])
        if value.startswith("License :: ")
    ]
    if classifiers:
        return " | ".join(classifiers), "Classifier"
    return "UNKNOWN", "missing"


def _render(manifest: dict[str, object]) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = _render(build_manifest())
    if args.check:
        if not args.output.is_file() or args.output.read_text() != rendered:
            print("dependency license manifest is missing or stale")
            return 1
        if '"license": "UNKNOWN"' in rendered:
            print("dependency license manifest contains UNKNOWN licenses")
            return 1
        print("dependency license manifest is current")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
