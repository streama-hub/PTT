import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from .audit_explicit_contexts import mismatches
from .verify_metadata import evaluate


def cases():
    prefixes = [
        "Example.2024.1080p.BluRay", "Example.S02E03.1080p.WEB-DL",
        "Example.S01.COMPLETE.1080p.WEB-DL", "[Group] Example - 03 [1080p]",
        "Example.2024.09.15.1080p.HDTV", "Example.2024.2160p.UHD.BluRay.REMUX",
    ]
    languages = [
        ("English", "en-US", [("French", "fr-FR"), ("Japanese", "ja-JP")]),
        ("Japanese", "ja-JP", [("English", "en-US"), ("Spanish", "es-ES")]),
        ("English", "en-US", [("fr-CA", "fr-CA"), ("pt-BR", "pt-BR")]),
    ]
    forms = ["{s}", "({s})", "[SDH] ({s})", "[Forced] ({s})", "SDH [{s}]", "[SDH {s}]"]
    for prefix, (audio, tag, subtitles), form, separator, wrapper, casing in itertools.product(
        prefixes, languages, forms, [", ", " / ", " + "],
        ["{tokens}", "[{tokens}]", "({tokens})"], [str, str.lower, str.upper],
    ):
        tokens = f"Audio: {audio}; Subs: " + form.format(s=separator.join(name for name, _ in subtitles))
        yield dict(kind="multilanguage_list", form=form, wrapper=wrapper,
                   title=prefix + " " + casing(wrapper.format(tokens=tokens)) + " x264-GRP",
                   expected=dict(audio_languages=[tag], subtitle_languages=[code for _, code in subtitles]))
    for prefix, (audio, tag, subtitles), casing in itertools.product(prefixes, languages, [str, str.lower, str.upper]):
        first, second = subtitles
        for tokens, expected_audio, expected_subs in [
            (f"Audio: {audio}; Subs: [{first[0]}]; Audio: {second[0]}", [tag, second[1]], [first[1]]),
            (f"Subs: [{first[0]}, {second[0]}]; Audio: {audio}", [tag], [first[1], second[1]]),
            (f"[Audio: {audio}] [Subs: {first[0]}, {second[0]}]", [tag], [first[1], second[1]]),
        ]:
            yield dict(kind="role_boundaries", title=prefix + " " + casing(tokens) + " x264-GRP",
                       expected=dict(audio_languages=expected_audio, subtitle_languages=expected_subs))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = list(cases())
    print(f"Multilanguage cases: {len(rows)}", flush=True)
    titles = [row["title"] for row in rows]
    before = evaluate(args.baseline, titles)
    after = evaluate(Path(__file__).resolve().parents[1], titles)
    assert len(rows) == len(before) == len(after)
    failures, unrelated = [], []
    for row, old, new in zip(rows, before, after):
        row.update(before=old, after=new)
        differences = mismatches(new.get("result", {}), row["expected"])
        if differences or "error" in new:
            previous = mismatches(old.get("result", {}), row["expected"])
            failures.append(dict(row, mismatches=differences, regressed_fields=[key for key in differences if key not in previous]))
        left = {k: v for k, v in old.get("result", {}).items() if k not in {"audio_languages", "subtitle_languages"}}
        right = {k: v for k, v in new.get("result", {}).items() if k not in {"audio_languages", "subtitle_languages"}}
        if left != right:
            unrelated.append(dict(title=row["title"], before=left, after=right))
    summary = dict(cases=len(rows), passed=len(rows) - len(failures), alerts=len(failures),
                   regressed_cases=sum(bool(row["regressed_fields"]) for row in failures),
                   exceptions=sum("error" in row for row in after), unrelated_changes=len(unrelated),
                   alert_types=dict(Counter(row["kind"] for row in failures)),
                   alert_forms=dict(Counter(row.get("form", "boundary") for row in failures)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(summary=summary, cases=rows, failures=failures, unrelated_changes=unrelated), ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return bool(failures or unrelated)


if __name__ == "__main__":
    raise SystemExit(main())
