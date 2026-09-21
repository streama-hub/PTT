import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from .verify_metadata import evaluate

LANGUAGES = [
    ("VOF", ["fr-FR"], []),
    ("VF", ["fr-FR"], []),
    ("VFF", ["fr-FR"], []),
    ("VFQ", ["fr-CA"], []),
    ("VFI", ["fr-FR"], []),
    ("VFB", ["fr-FR"], []),
    ("VF2", ["fr-FR"], []),
    ("TRUEFRENCH", ["fr-FR"], []),
    ("FRENCH", ["fr-FR"], []),
    ("VOSTFR", [], ["fr-FR"]),
    ("VOSTA", [], ["en-US"]),
    ("SUBFRENCH", [], ["fr-FR"]),
    ("ENGSUB", [], ["en-US"]),
    ("ESUB", [], ["en-US"]),
    ("MULTI", ["multi"], []),
    ("Multi-Subs", [], ["multi"]),
    ("MultiSubs", [], ["multi"]),
    ("MSUB", [], ["multi"]),
    ("JAPANESE", ["ja-JP"], []),
    ("ENGLISH", ["en-US"], []),
    ("GERMAN", ["de-DE"], []),
    ("SPANISH", ["es-ES"], []),
    ("VOF VOSTFR", ["fr-FR"], ["fr-FR"]),
    ("VOF VOSTA", ["fr-FR"], ["en-US"]),
    ("VOF SUBFRENCH", ["fr-FR"], ["fr-FR"]),
    ("VOF ENGSUB", ["fr-FR"], ["en-US"]),
    ("VOF Multi-Subs", ["fr-FR"], ["multi"]),
    ("JAPANESE VOSTFR", ["ja-JP"], ["fr-FR"]),
    ("ENGLISH SUBFRENCH", ["en-US"], ["fr-FR"]),
    ("VFQ VOSTFR", ["fr-CA"], ["fr-FR"]),
    ("MULTI VOSTFR", ["multi"], ["fr-FR"]),
    ("MULTI Multi-Subs", ["multi"], ["multi"]),
]


def cases():
    rows = []
    bases = ["Example.2024", "Example.S02E03", "Example.S01"]
    for (marker, audio, subs), base, separator, case in itertools.product(
        LANGUAGES, bases, [".", " ", "_"], [str.upper, str.lower, str.title]
    ):
        title = f"{base}.1080p.{case(marker)}.BluRay.x264-GRP".replace(".", separator)
        rows.append(dict(kind="audio_languages", marker=marker, title=title, expected=dict(audio_languages=audio, subtitle_languages=subs)))
    codecs = ["DTS-HD.MA", "DTS HD MA", "DTS.HD.Master.Audio", "DTS-HD.HRA", "DTS-HD", "DTS-X", "HE-AACv2", "AAC"]
    for codec, source, base, first in itertools.product(codecs, ["", "HDTV", "DVB", "BluRay", "WEB-DL"], bases, [False, True]):
        markers = f"{source}.{codec}" if first else f"{codec}.{source}"
        expected = source or None
        if source == "DVB":
            expected = "HDTV"
        rows.append(dict(kind="source", marker=codec, title=f"{base}.1080p.{markers}.x264-GRP", expected=dict(quality=expected)))
    for marker, base, case in itertools.product(["EXTENDED", "REMASTERED", "EXTENDED.REMASTERED"], bases, [str.upper, str.lower, str.title]):
        expected = {}
        if "EXTENDED" in marker:
            expected["extended"] = True
        if "REMASTERED" in marker:
            expected["remastered"] = True
        rows.append(dict(kind="edition", marker=marker, title=f"{base}.{case(marker)}.1080p.BluRay", expected=expected))
    return rows


def mismatches(result, expected):
    if "error" in result:
        return {"error": result}
    actual = result["result"]
    return {key: dict(expected=value, actual=actual.get(key)) for key, value in expected.items() if actual.get(key) != value}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = cases()
    titles = [row["title"] for row in rows]
    print(f"baseline and candidate: {len(rows)} assertions", flush=True)
    before = evaluate(args.baseline, titles)
    after = evaluate(Path(__file__).resolve().parents[1], titles)
    assert len(before) == len(after) == len(rows)
    failures, improvements, regressions = [], [], []
    for row, old, new in zip(rows, before, after):
        old_fail, new_fail = mismatches(old, row["expected"]), mismatches(new, row["expected"])
        row.update(before=old, after=new)
        if new_fail:
            failures.append(dict(row, mismatches=new_fail, baseline_mismatches=old_fail))
        if old_fail and not new_fail:
            improvements.append(row)
        regressed_fields = {key: value for key, value in new_fail.items() if key not in old_fail}
        if regressed_fields:
            regressions.append(dict(row, regressed_fields=regressed_fields))
    summary = dict(cases=len(rows), passed=len(rows) - len(failures), failed=len(failures), improved=len(improvements), regressed=len(regressions), failures_by_marker=dict(Counter(row["marker"] for row in failures)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(summary=summary, cases=rows, failures=failures, regressions=regressions), ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
