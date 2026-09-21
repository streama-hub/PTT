import argparse
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

from .verify_metadata import FIELDS, corpus, evaluate


def matrix():
    rows = []
    bases = (
        "Example.Movie.2024.1080p.BluRay",
        "Example.S02E03.1080p.WEB-DL",
        "Example.S01-S03.1080p.WEB-DL",
    )
    languages = (
        ("French", "fr-FR"),
        ("English", "en-US"),
        ("Japanese", "ja-JP"),
        ("German", "de-DE"),
        ("Spanish", "es-ES"),
        ("Korean", "ko-KR"),
        ("Italian", "it-IT"),
        ("Portuguese", "pt-BR"),
        ("fr-CA", "fr-CA"),
        ("en-GB", "en-GB"),
        ("pt-PT", "pt-PT"),
        ("zh-Hant-TW", "zh-Hant-TW"),
    )
    for base, (name, tag), pattern, prefix, separator, lower in itertools.product(
        bases,
        languages,
        (
            "[{name} (SDH)]",
            "[{name} (Forced)]",
            "[Subs: {name}]",
            "[Subtitles: {name} (SDH), fr-FR (Forced)]",
            "[Audio: {name}] [Subs: English]",
        ),
        (False, True),
        (" ", ".", "_"),
        (False, True),
    ):
        marker = pattern.format(name=name).replace(" ", separator)
        if lower:
            marker = marker.lower()
        if pattern.startswith("[Audio"):
            expected = {"audio_languages": [tag], "subtitle_languages": ["en-US"]}
            title = marker + " " + base if prefix else base + "." + marker
        else:
            expected = {
                "audio_languages": ["ja-JP"],
                "subtitle_languages": sorted(
                    {tag, "fr-FR"} if pattern.startswith("[Subtitles") else {tag}
                ),
            }
            title = (
                marker + " " + base if prefix else base + "." + marker
            ) + ".JAPANESE"
        rows.append(dict(kind="explicit_roles", title=title, expected=expected))
    codecs = (
        ("DTS-HD MA", "DTS-HD MA"),
        ("DTS-HD HRA", "DTS-HD HRA"),
        ("DTS-X", "DTS-X"),
        ("HE-AACv2", "HE-AACv2"),
        ("HE-AAC", "HE-AAC"),
        ("AAC", "AAC"),
        ("TrueHD", "TrueHD"),
    )
    hdrs = (
        ("HDR10", ["HDR10"], []),
        ("HDR10+", ["HDR10+"], []),
        ("HLG", ["HLG"], []),
        ("DV P8.1", ["DV"], ["8.1"]),
        ("HDR10 DV P7", ["HDR10", "DV"], ["7"]),
    )
    for base, (codec, audio), channel, (
        hdr,
        hdr_values,
        profiles,
    ), separator in itertools.product(
        bases,
        codecs,
        ("2.0", "5.1", "7.1", "5.1.2", "7.1.4"),
        hdrs,
        (" ", ".", "_"),
    ):
        marker = f"{codec} {channel} {hdr}".replace(" ", separator)
        rows.append(
            dict(
                kind="technical",
                title=base + "." + marker,
                expected=dict(
                    audio=[audio],
                    channels=[channel],
                    hdr=hdr_values,
                    dolby_vision_profiles=profiles,
                ),
            )
        )
    for base, marker in itertools.product(
        bases,
        ("VFQ VFF", "VFF VFQ", "MULTI VFF", "JAPANESE VOSTFR", "JAPANESE Multi-Subs"),
    ):
        audio = (
            ["fr-CA", "fr-FR"]
            if "VFQ" in marker
            else ["multi", "fr-FR"]
            if marker == "MULTI VFF"
            else ["ja-JP"]
        )
        subs = (
            ["fr-FR"]
            if "VOSTFR" in marker
            else ["multi"]
            if "Multi-Subs" in marker
            else []
        )
        rows.append(
            dict(
                kind="special",
                title=base + "." + marker,
                expected=dict(audio_languages=audio, subtitle_languages=subs),
            )
        )
    for base, (first, first_audio), (
        second,
        second_audio,
    ), separator in itertools.product(
        bases,
        codecs,
        codecs,
        (" ", ".", "_"),
    ):
        marker = f"{first} 7.1.4 {second} 2.0".replace(" ", separator)
        rows.append(
            dict(
                kind="multiple_audio_tracks",
                title=base + "." + marker,
                expected=dict(
                    audio=sorted({first_audio, second_audio}), channels=["7.1.4", "2.0"]
                ),
            )
        )
    for base, (name, tag), extension in itertools.product(
        bases,
        languages,
        ("srt", "ass", "ssa", "vtt"),
    ):
        rows.append(
            dict(
                kind="subtitle_files",
                title=f"{base}.{tag}.{extension}",
                expected=dict(audio_languages=[], subtitle_languages=[tag]),
            )
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--extra-corpus", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fingerprints = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "PTT").glob("*.py")
    }
    rows = [
        dict(kind="existing_corpus", title=t, expected={})
        for t in corpus([args.baseline / "tests", *args.extra_corpus])
    ]
    rows += matrix()
    outputs = {}
    for name, folder in (
        ("original", args.baseline),
        ("enriched", root),
    ):
        print(name, len(rows), flush=True)
        outputs[name] = evaluate(folder, [row["title"] for row in rows])
    failures = []
    for index, row in enumerate(rows):
        results = [outputs[name][index] for name in ("original", "enriched")]
        if any("error" in r for r in results):
            failures.append(dict(kind="exception", index=index, results=results))
            continue
        original, enriched = [r["result"] for r in results]
        changed = {
            k
            for k in original.keys() | enriched.keys()
            if original.get(k) != enriched.get(k)
        }
        if changed - FIELDS:
            failures.append(
                dict(kind="out_of_scope", index=index, fields=sorted(changed - FIELDS))
            )
        wrong = {
            k: dict(expected=v, actual=enriched.get(k, []))
            for k, v in row["expected"].items()
            if set(v) != set(enriched.get(k, []))
            or len(enriched.get(k, [])) != len(set(enriched.get(k, [])))
        }
        if wrong:
            failures.append(
                dict(
                    kind="semantic",
                    index=index,
                    group=row["kind"],
                    title=row["title"],
                    fields=wrong,
                )
            )
    assert fingerprints == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "PTT").glob("*.py")
    }
    summary = dict(
        cases=len(rows),
        unique_titles=len({r["title"] for r in rows}),
        corpus=sum(r["kind"] == "existing_corpus" for r in rows),
        failures=dict(Counter(f["kind"] for f in failures)),
        groups=dict(Counter(f.get("group", f["kind"]) for f in failures)),
        source_sha256=fingerprints,
    )
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
    raise SystemExit(main())
