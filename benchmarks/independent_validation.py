import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from .verify_metadata import evaluate


def cases():
    rows = []
    bases = ["Example.2024", "Example.S02E03", "Example.S01"]
    audio = [("VOF", "fr-FR"), ("French", "fr-FR"), ("VFQ", "fr-CA"), ("English", "en-US"), ("Japanese", "ja-JP"), ("MULTI", "multi")]
    subs = [("VOSTFR", "fr-FR"), ("VOSTA", "en-US"), ("ENGSUB", "en-US"), ("SUBFRENCH", "fr-FR"), ("Multi-Subs", "multi")]
    for (a, ac), (s, sc), first, case, separator, base in itertools.product(audio, subs, [True, False], [str.upper, str.lower, str.title], [".", " ", "_"], bases):
        marker = f"{a} {s}" if first else f"{s} {a}"
        title = f"{base}.1080p.{case(marker)}.WEB-DL.x264-GRP".replace(".", separator)
        rows.append(dict(kind="language_order", title=title, expected=dict(audio_languages=[ac], subtitle_languages=[sc], title="Example", quality="WEB-DL", codec="avc", group="GRP")))
    for lang, tag in audio:
        for suffix in ["srt", "ass", "ssa", "vtt"]:
            rows.append(dict(kind="subtitle_file", title=f"Example.S02E03.{lang}.{suffix}", expected=dict(audio_languages=[], subtitle_languages=[tag])))
    for codec, quality, edition, first in itertools.product(
        ["DTS-HD.MA", "DTS-HD.HRA", "DTS-HD", "DTS HD Master Audio"],
        ["", "HDTV", "HD", "WEB", "WEB-DL", "BluRay", "BDRip", "HDTVRip", "DVB", "PDTV"],
        ["", "EXTENDED", "REMASTERED", "EXTENDED.REMASTERED"], [True, False]
    ):
        markers = f"{codec}.{quality}" if first else f"{quality}.{codec}"
        expected = dict(quality=("HDTV" if quality in {"HD", "DVB"} else quality or None), title="Example", codec="hevc", resolution="2160p", group="GRP")
        if "EXTENDED" in edition:
            expected["extended"] = True
        if "REMASTERED" in edition:
            expected["remastered"] = True
        rows.append(dict(kind="technical_order", title=f"Example.2024.{edition}.2160p.{markers}.7.1.4.HDR10+.DV.P8.1.x265-GRP", expected=expected))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = cases()
    titles = [r["title"] for r in rows]
    print(f"Independent cases: {len(rows)}", flush=True)
    old = evaluate(args.baseline, titles)
    new = evaluate(Path(__file__).resolve().parents[1], titles)
    assert len(old) == len(new) == len(rows)
    failures = []
    for row, before, after in zip(rows, old, new):
        row.update(before=before, after=after)
        diffs = {k: dict(expected=v, actual=after.get("result", {}).get(k)) for k, v in row["expected"].items() if after.get("result", {}).get(k) != v}
        if "error" in after:
            diffs["error"] = after
        if diffs:
            previous = before.get("result", {})
            regressions = [k for k in diffs if k in row["expected"] and previous.get(k) == row["expected"][k]]
            failures.append(dict(row, mismatches=diffs, regressed_fields=regressions))
    summary = dict(cases=len(rows), passed=len(rows) - len(failures), failed=len(failures), regressions=sum(bool(r["regressed_fields"]) for r in failures), failure_types=dict(Counter(r["kind"] for r in failures)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(summary=summary, cases=rows, failures=failures), ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
