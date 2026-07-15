from __future__ import annotations

import ast
from pathlib import Path


def test_domain_and_application_do_not_import_framework_or_database() -> None:
    forbidden_roots = {"mcp", "pydantic", "sqlalchemy", "psycopg", "asyncpg"}
    roots = [Path("src/psr_mcp/domain"), Path("src/psr_mcp/application")]
    violations: list[str] = []
    for root in roots:
        for source_path in root.glob("*.py"):
            tree = ast.parse(source_path.read_text())
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                for name in names:
                    if name.split(".", maxsplit=1)[0] in forbidden_roots:
                        violations.append(f"{source_path}:{name}")
    assert violations == []
