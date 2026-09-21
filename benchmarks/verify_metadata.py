import argparse
import ast
import hashlib
import itertools
import json
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path


WORKER = """
import json, sys
from PTT import parse_title
output = []
for title in json.load(sys.stdin):
    try:
        result = parse_title(title)
        if 'languages' in result:
            result['audio_languages'] = result.pop('languages')
        output.append({'result': result})
    except Exception as error:
        output.append({'error': type(error).__name__, 'message': str(error)})
print(json.dumps(output))
"""
FIELDS = {
    "audio_languages",
    "subtitle_languages",
    "audio",
    "channels",
    "hdr",
    "dolby_vision_profiles",
}


def corpus(roots):
    titles = set()
    for root in roots:
        for path in root.rglob("test_*.py"):
            if any(part in (".venv", ".git", "node_modules") for part in path.parts):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and 25 < len(node.value) <= 4096
                    and any(
                        token in node.value
                        for token in ("1080", "720", "2160", "S01", "WEB-DL", "BluRay")
                    )
                ):
                    titles.add(node.value)
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "parametrize"
                    and len(node.args) > 1
                    and isinstance(node.args[1], (ast.List, ast.Tuple))
                ):
                    for row in node.args[1].elts:
                        first = (
                            row.elts[0]
                            if isinstance(row, (ast.List, ast.Tuple)) and row.elts
                            else row
                        )
                        if (
                            isinstance(first, ast.Constant)
                            and isinstance(first.value, str)
                            and len(first.value) <= 4096
                        ):
                            titles.add(first.value)
    return sorted(titles)


def evaluate(root, titles):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    output = []
    for start in range(0, len(titles), 300):
        run = subprocess.run(
            [sys.executable, "-c", WORKER],
            input=json.dumps(titles[start : start + 300]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=root,
            env=environment,
            timeout=60,
            check=True,
        )
        output.extend(json.loads(run.stdout))
    return output


def matrix():
    bases = [
        "Example.Movie.2024",
        "Example.S02E03",
        "Example.S01-S03",
        "[Group] Example Anime - 1177",
        "Example.S00E01",
        "La.Saison.Des.Femmes.2015",
    ]
    markers = [
        ("VFQ", {"audio_languages": ["fr-CA"], "subtitle_languages": []}),
        ("VFF", {"audio_languages": ["fr-FR"], "subtitle_languages": []}),
        ("JAPANESE VOSTFR", {"audio_languages": ["ja-JP"], "subtitle_languages": ["fr-FR"]}),
        ("[AAC ENG FRE]", {"audio_languages": ["en-US", "fr-FR"], "subtitle_languages": []}),
        ("legendado BR", {"subtitle_languages": ["pt-BR"]}),
        ("Dublado BR", {"audio_languages": ["pt-BR"]}),
        ("MULTI", {"audio_languages": ["multi"]}),
        ("Multi-Subs", {"subtitle_languages": ["multi"]}),
        ("DTS-HD MA 7.1.4", {"audio": ["DTS-HD MA"], "channels": ["7.1.4"]}),
        ("DTS-HD HRA 5.1", {"audio": ["DTS-HD HRA"], "channels": ["5.1"]}),
        ("HE-AACv2 5.1.2", {"audio": ["HE-AACv2"], "channels": ["5.1.2"]}),
        ("DTS 2.0", {"audio": ["DTS Lossy"], "channels": ["2.0"]}),
        ("AAC 2.0 HE-AACv2 5.1", {"audio": ["AAC", "HE-AACv2"]}),
        ("HDR10+ DV P8.1", {"hdr": ["DV", "HDR10+"], "dolby_vision_profiles": ["8.1"]}),
        ("HLG", {"hdr": ["HLG"]}),
        ("pt-PT", {"audio_languages": ["pt-PT"]}),
    ]
    rows = []
    for base, (marker, expected), separator, casing in itertools.product(
        bases, markers, (" ", ".", "_"), (str, str.lower, str.upper)
    ):
        wanted = dict(expected)
        if (
            "Saison" in base
            and "audio_languages" in wanted
            and "fr-CA" not in wanted["audio_languages"]
        ):
            wanted["audio_languages"] = list(dict.fromkeys(["fr-FR"] + wanted["audio_languages"]))
        rows.append(
            dict(
                title=base + ".1080p.BluRay." + casing(marker).replace(" ", separator),
                expected=wanted,
            )
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--extra-corpus", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, default=Path("dist/verification.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fingerprints = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "PTT").glob("*.py")
    }
    rows = [
        dict(title=t, expected={})
        for t in corpus([args.baseline / "tests", *args.extra_corpus])
    ]
    originals = list(rows)
    for row, separator in itertools.product(originals, (" ", ".", "_")):
        rows.append(dict(title=row["title"].replace(" ", separator), expected={}))
    rows += matrix()
    rng = random.Random(20260920)
    tokens = [
        "VFQ",
        "VOSTFR",
        "DTS-HD",
        "7.1.4",
        "HDR10+",
        "S02E03",
        "猫",
        "é",
        "العربية",
        "(",
        "]",
        " ",
        "Multi-Subs",
        "BEN.THE.MEN",
    ]
    rows += [
        dict(title=" ".join(rng.choices(tokens, k=rng.randint(1, 20))), expected={})
        for _ in range(300)
    ]
    rows += [
        dict(title=t, expected={}) for t in ("", "x" * 4096, "[" * 4096, "MULTI " * 500)
    ]
    titles = [row["title"] for row in rows]
    outputs = {}
    for name, folder in (("original", args.baseline), ("detailed", root)):
        print(name, len(rows), flush=True)
        outputs[name] = evaluate(folder, titles)
    failures = []
    changes = Counter()
    for index, row in enumerate(rows):
        old, detailed = (outputs[name][index] for name in ("original", "detailed"))
        if any("error" in item for item in (old, detailed)):
            failures.append(
                dict(kind="exception", index=index, original=old, detailed=detailed)
            )
            continue
        old, detailed = old["result"], detailed["result"]
        changed = {
            key
            for key in old.keys() | detailed.keys()
            if old.get(key) != detailed.get(key)
        }
        changes.update(changed)
        if changed - FIELDS:
            failures.append(
                dict(kind="out_of_scope", index=index, fields=sorted(changed - FIELDS))
            )
        wrong = {
            key: dict(expected=value, actual=detailed.get(key))
            for key, value in row["expected"].items()
            if detailed.get(key) != value
        }
        if wrong:
            failures.append(
                dict(kind="expected", index=index, title=row["title"], fields=wrong)
            )
    from PTT import parse_title

    shuffled = list(range(len(rows)))
    rng.shuffle(shuffled)
    for index in shuffled:
        if parse_title(titles[index]) != outputs["detailed"][index].get("result"):
            failures.append(dict(kind="state", index=index))
    summary = dict(
        cases=len(rows),
        unique_titles=len(set(titles)),
        annotated=sum(bool(row["expected"]) for row in rows),
        changed_fields=dict(changes),
        failures=dict(Counter(f["kind"] for f in failures)),
        repeat_checks=len(rows),
        baseline=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=args.baseline, text=True
        ).strip(),
        source_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root / "PTT").glob("*.py")
        },
    )
    if fingerprints != summary["source_sha256"]:
        raise RuntimeError("Parser changed during verification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            dict(summary=summary, failures=failures, cases=rows, results=outputs),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
