import argparse
import hashlib
import itertools
import json
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .verify_metadata import FIELDS, corpus, evaluate


def annotated():
    rows = []

    def add(kind, title, expected, interpretation="feature"):
        rows.append(
            dict(
                kind=kind, title=title, expected=expected, interpretation=interpretation
            )
        )

    for title, coordinate, language, separator in itertools.product(
        (
            "Forced",
            "The Subs Club",
            "The Subtitle",
            "Undertekst",
            "The Submarine",
            "Ordinary Story",
        ),
        ("2024", "S02E03", "S01-S03"),
        (("JAPANESE", "ja-JP"), ("FRENCH", "fr-FR"), ("ENGLISH", "en-US")),
        (" ", ".", "_"),
    ):
        raw = separator.join(
            (title.replace(" ", separator), coordinate, "1080p", language[0])
        )
        add(
            "title_role_collision",
            raw,
            {"audio_languages": [language[1]], "subtitle_languages": []},
            "regression_control",
        )

    markers = [
        ("VFQ", ["fr-CA"], []),
        ("VFF", ["fr-FR"], []),
        ("FRENCH VFQ", ["fr-CA"], []),
        ("VFF VFQ", ["fr-FR", "fr-CA"], []),
        ("JAPANESE VOSTFR", ["ja-JP"], ["fr-FR"]),
        ("VFQ VOSTFR", ["fr-CA"], ["fr-FR"]),
        ("[Audio EN-US EN-GB] [Subs FR-CA]", ["en-US", "en-GB"], ["fr-CA"]),
        ("[Subs pt-BR] [Audio pt-PT]", ["pt-PT"], ["pt-BR"]),
        ("[Audio ENG POL Subs FRE GER]", ["en-US", "pl-PL"], ["fr-FR", "de-DE"]),
        ("[Audio Japanese] [Subs FR,EN]", ["ja-JP"], ["fr-FR", "en-US"]),
        ("[AAC ENG FRE]", ["en-US", "fr-FR"], []),
        ("(eng-fre-pt-spa)", ["en-US", "fr-FR", "pt-BR", "es-ES"], []),
        ("Dublado BR", ["pt-BR"], []),
        ("legendado BR", [], ["pt-BR"]),
        ("[Subs Latin American Spanish]", [], ["es-419"]),
        ("MULTI", ["multi"], []),
        ("Multi-Subs", [], ["multi"]),
        ("JAPANESE FRENCH SUBBED", ["ja-JP"], ["fr-FR"]),
        ("SUBBED FRENCH", [], ["fr-FR"]),
    ]
    for (marker, audio, subtitles), base, separator, casing in itertools.product(
        markers,
        ("Example.2024", "Example.S02E03", "[Group] Example Anime - 1177"),
        (" ", ".", "_"),
        (str, str.upper, str.lower),
    ):
        add(
            "language_roles",
            base + ".1080p." + casing(marker).replace(" ", separator),
            dict(audio_languages=audio, subtitle_languages=subtitles),
        )
    for marker, audio, subtitles in markers:
        if marker.startswith("["):
            add(
                "labelled_prefix",
                marker + " Example.S02E03.1080p",
                dict(audio_languages=audio, subtitle_languages=subtitles),
            )
    for marker, code in (
        ("VFQ", "fr-CA"),
        ("VFF", "fr-FR"),
        ("French", "fr-FR"),
        ("Japanese", "ja-JP"),
        ("pt-PT", "pt-PT"),
    ):
        for extension in ("srt", "ass", "ssa", "vtt", "sub", "idx"):
            add(
                "subtitle_files",
                f"Example.S02E03.{marker}.{extension}",
                dict(audio_languages=[], subtitle_languages=[code]),
            )

    codecs = [
        ("DTS", "DTS Lossy"),
        ("DTS-HD MA", "DTS-HD MA"),
        ("DTS-HD HRA", "DTS-HD HRA"),
        ("DTS-X", "DTS-X"),
        ("AAC", "AAC"),
        ("HE-AACv2", "HE-AACv2"),
        ("TrueHD", "TrueHD"),
        ("DD+", "Dolby Digital Plus"),
        ("FLAC", "FLAC"),
        ("AC3", "Dolby Digital"),
    ]
    for left, right, base, separator, layouts in itertools.product(
        codecs,
        codecs,
        ("Example.2024", "Example.S02E03", "Example.S01-S03"),
        (" ", "."),
        (("2.0", "5.1"), ("5.1", "5.1.2"), ("7.1.4", "7.1")),
    ):
        raw = (
            base
            + ".1080p.BluRay."
            + separator.join(
                (
                    left[0].replace(" ", separator),
                    layouts[0],
                    right[0].replace(" ", separator),
                    layouts[1],
                )
            )
        )
        add(
            "codec_occurrences",
            raw,
            dict(
                audio=list(dict.fromkeys((left[1], right[1]))), channels=list(layouts)
            ),
        )
    hdrs = [
        ("HDR", "HDR"),
        ("HDR10", "HDR10"),
        ("HDR10+", "HDR10+"),
        ("HLG", "HLG"),
        ("DV P8.1", "DV"),
        ("SDR", "SDR"),
    ]
    for left, right, separator in itertools.product(hdrs, hdrs, (" ", ".", "_")):
        expected = {"hdr": list(dict.fromkeys((left[1], right[1])))}
        if "DV" in expected["hdr"]:
            expected["dolby_vision_profiles"] = ["8.1"]
        add(
            "hdr_occurrences",
            "Example.2024.2160p."
            + separator.join(
                (left[0].replace(" ", separator), right[0].replace(" ", separator))
            ),
            expected,
        )
    for codec, layout, suffix in itertools.product(
        ("AAC", "HE-AACv2", "TrueHD"), ("7.1.4", "5.1.2"), ("ch", "channels", "x2")
    ):
        add(
            "channel_suffixes",
            f"Example.2024.1080p.{codec}.{layout}{suffix}",
            {"channels": [layout]},
        )
    for text in (
        "Example.2024.1080p.[Audio EN-FR]",
        "Example.2024.1080p.[Audio EN-IT]",
        "Example.2024.1080p.Version.7.1.4",
        "Example.2024.1080p.7.1.4.GB",
        "Example.2024.1080p.Audio.French.Subs.English",
        "Example.2024.1080p.DV.P8.1.2",
    ):
        rows.append(
            dict(
                kind="exploratory",
                title=text,
                expected={},
                interpretation="manual_review",
            )
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--extra-corpus", type=Path, action="append", default=[])
    parser.add_argument(
        "--output", type=Path, default=Path("dist/deep-comparison.json")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fingerprints = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "PTT").glob("*.py")
    }
    rows = [
        dict(kind="corpus", title=t, expected={})
        for t in corpus([args.baseline / "tests", *args.extra_corpus])
    ]
    rows += annotated()
    outputs = {}
    for name, folder in (
        ("original", args.baseline),
        ("detailed", root),
    ):
        print(name, len(rows), flush=True)
        outputs[name] = evaluate(folder, [r["title"] for r in rows])
    failures = []
    changes = Counter()
    for index, row in enumerate(rows):
        responses = [outputs[name][index] for name in ("original", "detailed")]
        if any("error" in item for item in responses):
            failures.append(dict(kind="exception", index=index, responses=responses))
            continue
        original, detailed = [item["result"] for item in responses]
        changed = {
            key
            for key in original.keys() | detailed.keys()
            if original.get(key) != detailed.get(key)
        }
        changes.update(changed)
        if changed - FIELDS:
            failures.append(
                dict(kind="out_of_scope", index=index, fields=sorted(changed - FIELDS))
            )
        wrong = {}
        for field, expected in row["expected"].items():
            actual = detailed.get(field, [])
            if set(actual) != set(expected) or len(actual) != len(set(actual)):
                wrong[field] = dict(expected=expected, actual=actual)
        if wrong:
            failures.append(
                dict(
                    kind="semantic",
                    index=index,
                    test=row["kind"],
                    input=row["title"],
                    fields=wrong,
                    original=original,
                    detailed=detailed,
                )
            )
    from PTT import parse_title

    rng = random.Random(20260921)
    selected = rng.sample(range(len(rows)), min(400, len(rows)))
    with ThreadPoolExecutor(max_workers=8) as executor:
        concurrent = list(
            executor.map(lambda i: parse_title(rows[i]["title"]), selected)
        )
    concurrent_errors = sum(
        result != outputs["detailed"][i].get("result")
        for i, result in zip(selected, concurrent)
    )
    fingerprints_after = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "PTT").glob("*.py")
    }
    assert fingerprints == fingerprints_after, "Parser changed during audit"
    summary = dict(
        cases=len(rows),
        unique_titles=len({r["title"] for r in rows}),
        annotated=sum(bool(r["expected"]) for r in rows),
        failures=dict(Counter(f["kind"] for f in failures)),
        failed_tests=dict(Counter(f.get("test", f["kind"]) for f in failures)),
        changes=dict(changes),
        concurrent_checks=len(selected),
        concurrent_errors=concurrent_errors,
        source_sha256=fingerprints,
    )
    path = args.output
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            dict(summary=summary, failures=failures, cases=rows, results=outputs),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return bool(failures or concurrent_errors)


if __name__ == "__main__":
    sys.exit(main())
