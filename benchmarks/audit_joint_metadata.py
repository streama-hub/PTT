import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from .audit_explicit_contexts import cases as context_cases
from .audit_explicit_contexts import mismatches
from .verify_metadata import evaluate


def cases():
    markers = [
        ("VFQ VOSTFR", ["fr-CA"], ["fr-FR"]),
        ("VFF ENGSUB", ["fr-FR"], ["en-US"]),
        ("JAPANESE Multi-Subs", ["ja-JP"], ["multi"]),
        ("MULTI VOSTFR", ["multi"], ["fr-FR"]),
        ("[Audio: pt-BR; Subs: fr-CA, English]", ["pt-BR"], ["fr-CA", "en-US"]),
    ]
    technical = [row for row in context_cases() if row["kind"] == "technical_contexts"]
    for row, (marker, audio, subs), identity in itertools.product(technical, markers, ["Example.2024", "Example.S02E03", "Example.S01.COMPLETE"]):
        title = row["title"].replace("Example.2024", identity).replace(".x265-GRP", " " + marker + " x265-GRP")
        expected = dict(row["expected"], audio_languages=audio, subtitle_languages=subs)
        yield dict(title=title, marker=marker, expected=expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = list(cases())
    print(f"Joint metadata cases: {len(rows)}", flush=True)
    titles = [row["title"] for row in rows]
    old = evaluate(args.baseline, titles)
    new = evaluate(Path(__file__).resolve().parents[1], titles)
    assert len(rows) == len(old) == len(new)
    failures = []
    for row, before, after in zip(rows, old, new):
        row.update(before=before, after=after)
        differences = mismatches(after.get("result", {}), row["expected"])
        if differences or "error" in after:
            previous = mismatches(before.get("result", {}), row["expected"])
            failures.append(dict(row, mismatches=differences, regressed_fields=[key for key in differences if key not in previous]))
    summary = dict(cases=len(rows), passed=len(rows) - len(failures), alerts=len(failures),
                   regressed_cases=sum(bool(row["regressed_fields"]) for row in failures),
                   exceptions=sum("error" in row for row in new),
                   alert_fields=dict(Counter(key for row in failures for key in row["mismatches"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(summary=summary, cases=rows, failures=failures), ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
