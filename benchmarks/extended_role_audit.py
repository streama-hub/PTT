import argparse
import hashlib
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

from langcodes import Language

from .verify_metadata import FIELDS, corpus, evaluate


def matrix():
    rows = []
    markers = [
        ("VFQ", ["fr-CA"], []),
        ("VFF VFQ", ["fr-FR", "fr-CA"], []),
        ("JAPANESE VOSTFR", ["ja-JP"], ["fr-FR"]),
        ("KOREAN ENSUBBED", ["ko-KR"], ["en-US"]),
        ("MULTI", ["multi"], []),
        ("JAPANESE Multi-Subs", ["ja-JP"], ["multi"]),
        (
            "[Audio: Japanese] [Subtitles: English, French]",
            ["ja-JP"],
            ["en-US", "fr-FR"],
        ),
        (
            "[Subtitles: English, French] [Audio: Japanese]",
            ["ja-JP"],
            ["en-US", "fr-FR"],
        ),
        ("[Audio: Japanese / French] [Subs: English]", ["ja-JP", "fr-FR"], ["en-US"]),
        ("[Audio: Japanese; Subs: English, French]", ["ja-JP"], ["en-US", "fr-FR"]),
        (
            "[Audio: Japanese] [English SDH] [French Forced]",
            ["ja-JP"],
            ["en-US", "fr-FR"],
        ),
        (
            "[Audio: Japanese] [Subtitles: French, English (SDH)]",
            ["ja-JP"],
            ["fr-FR", "en-US"],
        ),
        (
            "[Audio: Japanese] [Subtitles: English (SDH), French]",
            ["ja-JP"],
            ["en-US", "fr-FR"],
        ),
        (
            "[Audio: Japanese] [Subtitles: English [SDH], French]",
            ["ja-JP"],
            ["en-US", "fr-FR"],
        ),
        (
            "[Audio: Japanese] [Subtitles: English (Forced), French]",
            ["ja-JP"],
            ["en-US", "fr-FR"],
        ),
        (
            "[Audio: Japanese (AAC), French] [Subtitles: English]",
            ["ja-JP", "fr-FR"],
            ["en-US"],
        ),
        ("[Audio: en-US] [Subtitles: en-GB]", ["en-US"], ["en-GB"]),
        ("[Audio: fr-CA fr-FR] [Subtitles: fr-FR]", ["fr-CA", "fr-FR"], ["fr-FR"]),
        ("[Audio: pt-PT] [Subtitles: pt-BR]", ["pt-PT"], ["pt-BR"]),
        ("[Audio: zh-Hant-TW] [Subtitles: zh-Hans-CN]", ["zh-Hant-TW"], ["zh-Hans-CN"]),
    ]
    bases = ("Example.Movie.2024", "Example.S02E03", "[Group] Example Anime - 1177")
    for base, (marker, audio, subtitles), separator, casing in itertools.product(
        bases, markers, (" ", ".", "_"), (str, str.lower, str.upper)
    ):
        rows.append(
            dict(
                kind="language_roles",
                title=base + ".1080p.WEB-DL." + casing(marker).replace(" ", separator),
                expected={"audio_languages": audio, "subtitle_languages": subtitles},
                constructed=True,
            )
        )
    for base, label, opening, closing, separator in itertools.product(
        bases, ("Subs", "Subtitles"), ("[", "("), ("]", ")"), (" ", ".", "_")
    ):
        if (opening, closing) not in (("[", "]"), ("(", ")")):
            continue
        prefix = opening + label + " English, French" + closing
        rows.append(
            dict(
                kind="prefix_blocks",
                title=prefix.replace(" ", separator) + " " + base + ".1080p.JAPANESE",
                expected={
                    "audio_languages": ["ja-JP"],
                    "subtitle_languages": ["en-US", "fr-FR"],
                },
                constructed=True,
            )
        )
    for base, code, label in itertools.product(
        bases,
        (
            "fr-FR",
            "fr-CA",
            "en-US",
            "en-GB",
            "pt-BR",
            "pt-PT",
            "es-419",
            "zh-Hant-TW",
            "zh-Hans-CN",
            "ja-JP",
            "ko-KR",
            "de-DE",
        ),
        ("Audio", "Subs"),
    ):
        expected = {
            "audio_languages": [code] if label == "Audio" else [],
            "subtitle_languages": [code] if label == "Subs" else [],
        }
        rows.append(
            dict(
                kind="explicit_regions",
                title=f"{base}.1080p.[{label}: {code}]",
                expected=expected,
                constructed=True,
            )
        )
    codecs = [
        ("DTS-HD MA", "DTS-HD MA"),
        ("DTS-HD HRA", "DTS-HD HRA"),
        ("DTS-X", "DTS-X"),
        ("HE-AACv2", "HE-AACv2"),
        ("AAC", "AAC"),
        ("TrueHD", "TrueHD"),
    ]
    for base, (marker, codec), channel, hdr, separator in itertools.product(
        bases,
        codecs,
        ("2.0", "5.1", "7.1.4"),
        ("HDR10+", "HLG", "DV P8.1"),
        (" ", ".", "_"),
    ):
        title = (
            f"{base}.2160p.BluRay."
            + separator.join((marker, channel, hdr)).replace(" ", separator)
            + ".mkv"
        )
        expected = dict(
            audio=[codec], channels=[channel], hdr=["DV" if hdr == "DV P8.1" else hdr]
        )
        if hdr == "DV P8.1":
            expected["dolby_vision_profiles"] = ["8.1"]
        rows.append(
            dict(
                kind="technical_combinations",
                title=title,
                expected=expected,
                constructed=True,
            )
        )
    for base, code, suffix in itertools.product(
        bases,
        ("fr-CA", "fr-FR", "en-US", "pt-PT", "zh-Hant-TW"),
        ("srt", "ass", "ssa", "vtt", "sub", "idx"),
    ):
        rows.append(
            dict(
                kind="subtitle_files",
                title=f"{base}.{code}.{suffix}",
                expected={"audio_languages": [], "subtitle_languages": [code]},
                constructed=True,
            )
        )
    return rows


def base_languages(values):
    return {
        "es" if value == "la" else Language.get(value).language
        for value in values
        if value != "multi"
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--extra-corpus", type=Path, action="append", default=[])
    parser.add_argument(
        "--output", type=Path, default=Path("dist/extended-role-audit.json")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    def sources():
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root / "PTT").glob("*.py")
        }

    before = sources()
    rows = [
        dict(kind="existing_corpus", title=title, expected={}, constructed=False)
        for title in corpus([args.baseline / "tests", *args.extra_corpus])
    ]
    rows += matrix()
    output = {}
    for name, folder in (
        ("original", args.baseline),
        ("enriched", root),
    ):
        print(name, len(rows), flush=True)
        output[name] = evaluate(folder, [row["title"] for row in rows])
    failures = []
    for index, row in enumerate(rows):
        old, new = [output[name][index] for name in ("original", "enriched")]
        if any("error" in result for result in (old, new)):
            failures.append(dict(kind="exception", index=index))
            continue
        old, new = (result["result"] for result in (old, new))
        changed = {
            key for key in old.keys() | new.keys() if old.get(key) != new.get(key)
        }
        if changed - FIELDS:
            failures.append(
                dict(kind="out_of_scope", index=index, fields=sorted(changed - FIELDS))
            )
        lost = base_languages(old["audio_languages"]) - base_languages(
            new["audio_languages"] + new["subtitle_languages"]
        )
        if lost:
            failures.append(
                dict(kind="native_language_loss", index=index, audio_languages=sorted(lost))
            )
        wrong = {
            field: dict(expected=values, actual=new.get(field, []))
            for field, values in row["expected"].items()
            if set(new.get(field, [])) != set(values)
            or len(new.get(field, [])) != len(set(new.get(field, [])))
        }
        if wrong:
            failures.append(
                dict(
                    kind="semantic",
                    index=index,
                    test=row["kind"],
                    title=row["title"],
                    fields=wrong,
                )
            )
    assert before == sources(), "Parser changed during audit"
    summary = dict(
        cases=len(rows),
        unique_titles=len({row["title"] for row in rows}),
        existing_corpus=sum(not row["constructed"] for row in rows),
        annotated=sum(bool(row["expected"]) for row in rows),
        failures=dict(Counter(row["kind"] for row in failures)),
        semantic_groups=dict(
            Counter(row["test"] for row in failures if row["kind"] == "semantic")
        ),
        source_sha256=before,
    )
    path = args.output
    path.write_text(
        json.dumps(
            dict(summary=summary, cases=rows, results=output, failures=failures),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
