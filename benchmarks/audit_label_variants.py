import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from .audit_explicit_contexts import mismatches
from .verify_metadata import evaluate


def cases():
    subtitles = [("French", "fr-FR"), ("Japanese", "ja-JP"), ("English", "en-US"), ("fr-CA", "fr-CA"), ("pt-BR", "pt-BR"), ("es-419", "es-419"), ("ENG", "en-US"), ("zh-Hant-TW", "zh-Hant-TW")]
    labels = ["Subs: {s}", "Subs {s}", "Subtitles: {s}", "Subs: SDH {s}", "Subs: Forced {s}", "Subs: {s} (SDH)", "Subs: [{s}]", "Subs: ({s})"]
    for (a, ac), (s, sc), label, layout, casing in itertools.product(
        [("English", "en-US"), ("Japanese", "ja-JP")],
        subtitles,
        labels,
        ["[Audio: {a}; {label}]", "Audio: {a}; {label}", "[Audio: {a}] [{label}]"],
        [str, str.lower, str.upper],
    ):
        tokens = casing(layout.format(a=a, label=label.format(s=s)))
        yield dict(kind="explicit_roles", label=label, layout=layout, title=f"Example.S02E03.1080p.WEB-DL {tokens} x264-GRP", expected=dict(audio_languages=[ac], subtitle_languages=[sc], title="Example", seasons=[2], episodes=[3], quality="WEB-DL", group="GRP"))
    for suffix, case, extension in itertools.product(
        ["Subs", "SDH", "Forced", "Subs: SDH", "Subs: Forced", "Subs:", "SDH:", "Forced:"],
        [str, str.lower, str.upper],
        ["", ".srt", ".ass"],
    ):
        yield dict(kind="annotations", title="Example.S02E03.1080p." + case("English " + suffix) + extension, expected=dict(audio_languages=[], subtitle_languages=["en-US"]))
    for title in [
        "Example.2024.1080p.English Undertekst: French.WEB-DL",
        "Example.2024.1080p.English SDH: French.WEB-DL",
        "Example.2024.1080p.English Forced: French.WEB-DL",
        "Example.2024.1080p.English Subs: Commentary.WEB-DL",
        "Example.2024.1080p.English Subs: None.WEB-DL",
    ]:
        yield dict(kind="exploratory", title=title, expected={})
    from PTT.metadata import transform_language
    from PTT.parse import LANGUAGES_TRANSLATION_TABLE

    for code, name in LANGUAGES_TRANSLATION_TABLE.items():
        for tokens, expected in [
            (f"[Audio: {name}] [Subs: English]", dict(audio_languages=[transform_language(code)], subtitle_languages=["en-US"])),
            (f"[Audio: Japanese] [Subs: {name}]", dict(audio_languages=["ja-JP"], subtitle_languages=[transform_language(code)])),
        ]:
            yield dict(kind="language_table_roles", title=f"Example.S01E01.1080p.WEB-DL {tokens} x264-GRP", expected=expected)


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
    summary = dict(
        cases=len(rows),
        specified=sum(bool(row["expected"]) for row in rows),
        alerts=len(failures),
        changed=len(changes),
        regressed_cases=sum(bool(row["regressed_fields"]) for row in failures),
        exceptions=sum("error" in row for row in new),
        alert_types=dict(Counter(row.get("label", row["kind"]) for row in failures)),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(summary=summary, cases=rows, failures=failures, changes=changes), ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
