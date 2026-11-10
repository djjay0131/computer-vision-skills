"""Check that MCP tool names written in skills exist in the Roboflow MCP tool catalog.

AUTHORING.md asks authors not to name tools that don't exist. This script checks
that rule mechanically: it finds backticked identifiers in skill Markdown that look
like MCP tool names and reports any that are not in the tool catalog.

The catalog is the public tool catalog pinned in cowork/catalog.json (URL and
SHA-256). Pass --catalog to use a downloaded copy offline; its hash is still checked
unless --no-verify is given (useful when testing against a newer, unpinned export).

Usage:
    python3 checks/check_tool_names.py                 # download the pinned catalog
    python3 checks/check_tool_names.py --catalog tools.json
    python3 checks/check_tool_names.py --strict        # exit 1 on unknown names
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIRS = ("skills", "chatgpt/skills")
ALLOWLIST = Path(__file__).with_name("not-tools.txt")

# Tool names end in a verb more often than not (`models_list`, `cases_create`).
# A name with one of these endings is checked even when its prefix is new.
TOOL_VERBS = {"get", "list", "create", "delete", "update", "run", "search", "validate", "upload",
              "set", "cancel", "start", "import", "replace", "preview", "launch", "infer", "publish",
              "trigger", "resume", "remove", "compare", "save", "download", "export"}

# `models_infer`, `models_infer(...)`, `workflows_run(workflow_id=…)`
CANDIDATE = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)(?:\([^`]*\))?`")


def load_catalog(catalog_path: Path | None, verify: bool = True) -> dict:
    pin = json.loads((ROOT / "cowork/catalog.json").read_text(encoding="utf-8"))
    if catalog_path is None:
        if not pin["url"].startswith("https://"):
            raise ValueError("catalog URL must use HTTPS")
        with urllib.request.urlopen(pin["url"], timeout=60) as response:
            data = response.read()
    else:
        data = catalog_path.read_bytes()
    if verify and hashlib.sha256(data).hexdigest() != pin["sha256"]:
        raise ValueError("Tool catalog SHA-256 does not match cowork/catalog.json")
    return json.loads(data)


def catalog_names(catalog: dict) -> tuple[set[str], set[str]]:
    """Return (tool names, parameter names) from a catalog with a `tools` list."""
    tools, params = set(), set()
    for tool in catalog["tools"]:
        tools.add(tool["name"])
        params.update(_property_names(tool.get("inputSchema", {})))
    return tools, params


def _property_names(schema: object) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, dict):
        for key, value in schema.get("properties", {}).items():
            names.add(key)
            names |= _property_names(value)
        for key in ("items", "anyOf", "oneOf", "allOf", "$defs", "definitions"):
            child = schema.get(key)
            children = child.values() if isinstance(child, dict) and key in ("$defs", "definitions") else (
                child if isinstance(child, list) else [child])
            for item in children:
                names |= _property_names(item)
    return names


def load_allowlist(path: Path = ALLOWLIST) -> set[str]:
    if not path.is_file():
        return set()
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return {line for line in lines if line}


def find_unknown(root: Path, tools: set[str], params: set[str], allow: set[str]) -> list[tuple[str, int, str]]:
    """Return (path, line, name) for tool-like names that are not in the catalog.

    A backticked identifier counts as a tool reference when its first segment is the
    first segment of a real tool (`workflows_`, `models_`, `project_`, …) or its last
    segment is a common tool verb (`_create`, `_list`, …), or it is the tail of a
    real tool name (`exports_get_job` for `workflow_evals_exports_get_job`), and it is not a known
    parameter name or an allowlisted identifier.
    """
    prefixes = {name.split("_", 1)[0] for name in tools}
    found = []
    for skill_dir in SKILL_DIRS:
        base = root / skill_dir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            relative = path.relative_to(root).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for name in CANDIDATE.findall(line):
                    if name in tools or name in params or name in allow:
                        continue
                    if (name.split("_", 1)[0] not in prefixes and name.rsplit("_", 1)[1] not in TOOL_VERBS
                            and not any(tool.endswith("_" + name) for tool in tools)):
                        continue
                    found.append((relative, number, name))
    return found


def suggestion(name: str, tools: set[str]) -> str | None:
    """The full tool name when `name` is a shortened form of exactly one tool."""
    matches = sorted(tool for tool in tools if tool.endswith("_" + name))
    return matches[0] if len(matches) == 1 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalog", type=Path, help="Use a downloaded tool catalog instead of fetching the pin")
    parser.add_argument("--no-verify", action="store_true", help="Skip the pinned SHA-256 check")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when unknown names are found")
    parser.add_argument("--github", action="store_true", help="Emit GitHub Actions warning annotations")
    args = parser.parse_args(argv)

    tools, params = catalog_names(load_catalog(args.catalog, verify=not args.no_verify))
    unknown = find_unknown(ROOT, tools, params, load_allowlist())
    for path, number, name in unknown:
        message = f"`{name}` is not in the MCP tool catalog"
        full = suggestion(name, tools)
        if full:
            message += f"; did you mean `{full}`?"
        if args.github:
            print(f"::warning file={path},line={number}::{message}")
        else:
            print(f"{path}:{number}: {message}")
    distinct = sorted({name for _, _, name in unknown})
    print(f"{len(tools)} catalog tools; {len(distinct)} unknown tool-like names in skills"
          + (": " + ", ".join(distinct) if distinct else ""))
    return 1 if unknown and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
