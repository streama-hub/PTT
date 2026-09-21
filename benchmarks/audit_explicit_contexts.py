import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from .verify_metadata import evaluate


def cases():
    languages = [
        ("Japanese", "ja-JP"),
        ("English", "en-US"),
        ("French", "fr-FR"),
        ("fr-CA", "fr-CA"),
        ("pt-PT", "pt-PT"),
        ("pt-BR", "pt-BR"),
        ("es-419", "es-419"),
        ("zh-Hant-TW", "zh-Hant-TW"),
    ]
    templates = [
        "[Audio: {a}] [Subs: {s}]",
        "[Subs: {s}] [Audio: {a}]",
        "Audio: {a} Subs: {s}",
        "Subs: {s} Audio: {a}",
        "[Audio: {a} (Stereo)] [Subs: {s} (SDH)]",
        "[Audio: {a}] [Subs: [{s}]]",
        "Audio [{a}] Subs [{s}]",
        "[Audio: {a}; Subs: {s}]",
    ]
    for (a, ac), (s, sc), template, casing in itertools.product(languages, languages, templates, [str, str.lower, str.upper]):
        yield dict(
            kind="explicit_roles",
            title="Example.S02E03.1080p.WEB-DL " + casing(template.format(a=a, s=s)) + " x264-GRP",
            expected=dict(audio_languages=[ac], subtitle_languages=[sc], title="Example", quality="WEB-DL", codec="avc", seasons=[2], episodes=[3], group="GRP"),
        )
    for (audio, expected_audio), channels, (hdr, expected_hdr), source in itertools.product(
        [("DTS-HD MA", "DTS-HD MA"), ("DTS-HD HRA", "DTS-HD HRA"), ("DTS-HD", "DTS-HD"), ("HE-AACv2", "HE-AACv2"), ("HE-AAC", "HE-AAC"), ("DTS:X", "DTS-X")],
        ["5.1.2", "7.1.4", "9.1.6"],
        [("HDR10", "HDR10"), ("HDR10+", "HDR10+"), ("HLG", "HLG"), ("DV P8.1", "DV"), ("Dolby Vision Profile 5", "DV")],
        ["BluRay", "WEB-DL", "HDTV", "BDRip"],
    ):
        expected = dict(audio=[expected_audio], channels=[channels], hdr=[expected_hdr], quality=source, title="Example", codec="hevc", resolution="2160p", group="GRP")
        if hdr in {"DV P8.1", "Dolby Vision Profile 5"}:
            expected["dolby_vision_profiles"] = ["8.1" if hdr == "DV P8.1" else "5"]
        yield dict(kind="technical_contexts", title=f"Example.2024.2160p.{source}.{audio}.{channels}.{hdr}.x265-GRP", expected=expected)
    for marker, tag in [("VOF", "fr-FR"), ("VFQ", "fr-CA"), ("VFF", "fr-FR"), ("MULTI", "multi")]:
        for extension in ["srt", "ass", "ssa", "vtt", "sub", "idx", "smi", "ttxt"]:
            yield dict(kind="subtitle_files", title=f"Example.S02E03.{marker}.{extension}", expected=dict(audio_languages=[], subtitle_languages=[tag]))


def mismatches(result, expected):
    return {key: dict(expected=value, actual=result.get(key)) for key, value in expected.items() if (set(result.get(key, [])) != set(value) if isinstance(value, list) else result.get(key) != value)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = list(cases())
    titles = [row["title"] for row in rows]
    before = evaluate(args.baseline, titles)
    after = evaluate(Path(__file__).resolve().parents[1], titles)
    assert len(rows) == len(before) == len(after)
    failures = []
    for row, old, new in zip(rows, before, after):
        row.update(before=old, after=new)
        differences = mismatches(new.get("result", {}), row["expected"])
        if differences or "error" in new:
            previous = mismatches(old.get("result", {}), row["expected"])
            failures.append(dict(row, mismatches=differences, regressed_fields=[key for key in differences if key not in previous]))
    summary = dict(cases=len(rows), passed=len(rows) - len(failures), alerts=len(failures), regressed_cases=sum(bool(row["regressed_fields"]) for row in failures), exceptions=sum("error" in row for row in after), alert_types=dict(Counter(row["kind"] for row in failures)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(summary=summary, cases=rows, failures=failures), indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
