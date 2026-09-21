import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from .audit_explicit_contexts import mismatches
from .verify_metadata import evaluate


def cases():
    formats = ["{annotation} {s}", "[{annotation} {s}]", "({annotation}) {s}", "[{annotation}] {s}", "{annotation} [{s}]", "{annotation} ({s})", "{s} ({annotation})", "[{s} {annotation}]"]
    for (a, ac), (s, sc), annotation, form, role, wrapping, casing in itertools.product(
        [("English", "en-US"), ("Japanese", "ja-JP"), ("VOF", "fr-FR")],
        [("French", "fr-FR"), ("fr-CA", "fr-CA"), ("Japanese", "ja-JP")],
        ["SDH", "Forced"],
        formats,
        ["Audio", "Dubbed"],
        ["{tokens}", "[{tokens}]", "({tokens})"],
        [str, str.lower, str.upper],
    ):
        tokens = wrapping.format(tokens=f"{role}: {a}; Subs: " + form.format(annotation=annotation, s=s))
        yield dict(kind="nested_roles", form=form, audio=a, title="Example.S02E03.1080p.WEB-DL " + casing(tokens) + " x264-GRP", expected=dict(audio_languages=[ac], subtitle_languages=[sc], title="Example", seasons=[2], episodes=[3], quality="WEB-DL", codec="avc", group="GRP"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = list(cases())
    titles = [row["title"] for row in rows]
    old = evaluate(args.baseline, titles)
    new = evaluate(Path(__file__).resolve().parents[1], titles)
    assert len(rows) == len(old) == len(new)
    failures, changes = [], []
    for row, before, after in zip(rows, old, new):
        row.update(before=before, after=after)
        differences = mismatches(after.get("result", {}), row["expected"])
        if differences or "error" in after:
            previous = mismatches(before.get("result", {}), row["expected"])
            failures.append(dict(row, mismatches=differences, regressed_fields=[key for key in differences if key not in previous]))
        if before != after:
            changes.append(row)
    summary = dict(cases=len(rows), passed=len(rows) - len(failures), alerts=len(failures), changed=len(changes), regressed_cases=sum(bool(row["regressed_fields"]) for row in failures), exceptions=sum("error" in row for row in new), alert_types=dict(Counter(row["form"] for row in failures)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(summary=summary, cases=rows, failures=failures, changes=changes), ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
