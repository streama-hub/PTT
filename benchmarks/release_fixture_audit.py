import argparse
import ast
import json
import subprocess
from pathlib import Path

from .verify_metadata import evaluate


def upstream_fixtures(root):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision, "tests"], cwd=root, text=True).splitlines()
    origins = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        source = subprocess.check_output(["git", "show", revision + ":" + path], cwd=root, encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "parametrize" or len(node.args) < 2:
                continue
            field, values = node.args[:2]
            if not isinstance(field, ast.Constant) or not isinstance(field.value, str) or field.value.split(",")[0].strip() != "release_name":
                continue
            if not isinstance(values, (ast.List, ast.Tuple)):
                raise ValueError(f"Unsupported fixture container: {path}:{node.lineno}")
            for row in values.elts:
                if not isinstance(row, (ast.Tuple, ast.List)) or not row.elts or not isinstance(row.elts[0], ast.Constant) or not isinstance(row.elts[0].value, str):
                    raise ValueError(f"Unsupported fixture row: {path}:{row.lineno}")
                origins.setdefault(row.elts[0].value, []).append(f"{path}:{row.lineno}")
    return revision, origins


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    revision, origins = upstream_fixtures(root)
    titles = sorted(origins)
    assert titles
    before = evaluate(args.baseline, titles)
    after = evaluate(root, titles)
    assert len(titles) == len(before) == len(after)
    rows = [dict(title=title, origins=origins[title], before=old, after=new) for title, old, new in zip(titles, before, after)]
    changes = [row for row in rows if row["before"] != row["after"]]
    errors = [row for row in rows if "error" in row["before"] or "error" in row["after"]]
    summary = dict(upstream_revision=revision, distinct_inputs=len(titles), fixture_occurrences=sum(map(len, origins.values())), changes=len(changes), errors=len(errors))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(summary=summary, cases=rows, changes=changes, errors=errors), ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return bool(changes or errors)


if __name__ == "__main__":
    raise SystemExit(main())
