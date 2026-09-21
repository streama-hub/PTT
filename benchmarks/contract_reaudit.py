import argparse
import hashlib
import itertools
import json
import random
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PTT import parse_title
from PTT.metadata import transform_language
from PTT.parse import LANGUAGES_TRANSLATION_TABLE

from .verify_metadata import FIELDS, evaluate


def matrix():
    rows = []

    def add(kind, marker, expected, base="Example.S02E03.1080p.WEB-DL."):
        rows.append(
            dict(kind=kind, title=base + marker, expected=expected, constructed=True)
        )

    for code, name in LANGUAGES_TRANSLATION_TABLE.items():
        if code == "la":
            continue
        tag = transform_language(code)
        for role, label, opening, closing in itertools.product(
            ("audio_languages", "subtitle_languages"), (name, code), ("[", "("), ("]", ")")
        ):
            if (opening, closing) not in (("[", "]"), ("(", ")")):
                continue
            expected = dict(audio_languages=[], subtitle_languages=[])
            expected[role] = [tag]
            add(
                "explicit_language_role",
                opening
                + ("Audio: " if role == "audio_languages" else "Subs: ")
                + label
                + closing,
                expected,
            )

    markers = [
        ("[Audio: Japanese] [English SDH]", ["ja-JP"], ["en-US"]),
        ("[Audio: Japanese] [English (SDH)]", ["ja-JP"], ["en-US"]),
        ("[Audio: Japanese] [English [SDH]]", ["ja-JP"], ["en-US"]),
        ("[Audio: Japanese] [English {SDH}]", ["ja-JP"], ["en-US"]),
        ("[Audio: Japanese] [English (Forced)]", ["ja-JP"], ["en-US"]),
        (
            "[Audio: Japanese] [English (SDH)] [Audio: English]",
            ["ja-JP", "en-US"],
            ["en-US"],
        ),
        ("[Audio: Japanese] [Subs: English (SDH)]", ["ja-JP"], ["en-US"]),
        (
            "[Audio: Japanese] [Subs: English (SDH), French]",
            ["ja-JP"],
            ["en-US", "fr-FR"],
        ),
        (
            "[Audio: Japanese] [Subs: English, French (SDH)]",
            ["ja-JP"],
            ["en-US", "fr-FR"],
        ),
        (
            "[Audio: Japanese] [Subs: English] [Audio: French]",
            ["ja-JP", "fr-FR"],
            ["en-US"],
        ),
        (
            "[Audio: English (AAC), Japanese] [Subs: French]",
            ["ja-JP", "en-US"],
            ["fr-FR"],
        ),
        ("English Subs[French, German]", ["en-US"], ["fr-FR", "de-DE"]),
        ("[Subs: French] [Audio: English (AAC)]", ["en-US"], ["fr-FR"]),
        ("JAPANESE VOSTFR", ["ja-JP"], ["fr-FR"]),
        ("VFF VFQ VOSTFR", ["fr-FR", "fr-CA"], ["fr-FR"]),
        ("[Audio: en-US en-GB] [Subs: en-US]", ["en-US", "en-GB"], ["en-US"]),
        ("[Audio: pt-PT] [Subs: pt-BR]", ["pt-PT"], ["pt-BR"]),
        ("[Multi-Audio] [Multi-Subs]", ["multi"], ["multi"]),
    ]
    for (marker, audio, subtitles), base, sep, casing in itertools.product(
        markers,
        (
            "Example.2024.1080p.",
            "Example.S02E03.1080p.",
            "[Group] Example - 1177 [1080p] ",
        ),
        (" ", ".", "_"),
        (str, str.lower, str.upper),
    ):
        add(
            "adjacent_role_forms",
            casing(marker).replace(" ", sep),
            dict(audio_languages=audio, subtitle_languages=subtitles),
            base,
        )

    codecs = [
        ("DTS-HD MA", "DTS-HD MA"),
        ("HE-AACv2", "HE-AACv2"),
        ("TrueHD", "TrueHD"),
        ("DTS-HD HRA", "DTS-HD HRA"),
    ]
    for (marker, audio, subtitles), (codec, expected), layout in itertools.product(
        markers, codecs, ("2.0", "7.1.4")
    ):
        add(
            "role_technical_composition",
            marker + " " + codec + " " + layout + " HDR10+ DV P8.1",
            dict(
                audio_languages=audio,
                subtitle_languages=subtitles,
                audio=(["AAC"] if "(AAC)" in marker else []) + [expected],
                channels=[layout],
                hdr=["HDR10+", "DV"],
                dolby_vision_profiles=["8.1"],
            ),
        )

    for marker, expected in (
        ("DTS-HD MA", dict(audio=["DTS-HD MA"])),
        ("HE-AACv2", dict(audio=["HE-AACv2"])),
        ("DV P8.1", dict(hdr=["DV"], dolby_vision_profiles=["8.1"])),
        ("DV", dict(hdr=["DV"], dolby_vision_profiles=[])),
        ("HDR10+", dict(hdr=["HDR10+"], dolby_vision_profiles=[])),
    ):
        for separator, case in itertools.product(
            (" ", ".", "_"), (str, str.upper, str.lower)
        ):
            add("technical_forms", case(marker).replace(" ", separator), expected)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("dist/contract-reaudit.json")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "PTT").glob("*.py")
    }
    rows = matrix()
    results = {}
    for key, path in (
        ("original", args.baseline),
        ("enriched", root),
    ):
        print(key, len(rows), flush=True)
        results[key] = evaluate(path, [r["title"] for r in rows])
    failures = []
    for index, row in enumerate(rows):
        old, new = [results[key][index] for key in ("original", "enriched")]
        if any("error" in r for r in (old, new)):
            failures.append(dict(index=index, kind="exception"))
            continue
        old, new = [r["result"] for r in (old, new)]
        changed = {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
        if changed - FIELDS:
            failures.append(
                dict(index=index, kind="out_of_scope", fields=sorted(changed - FIELDS))
            )
        wrong = {
            field: dict(expected=value, actual=new.get(field, []))
            for field, value in row["expected"].items()
            if set(new.get(field, [])) != set(value)
            or len(new.get(field, [])) != len(set(new.get(field, [])))
        }
        if wrong:
            failures.append(
                dict(
                    index=index,
                    kind="semantic",
                    group=row["kind"],
                    title=row["title"],
                    fields=wrong,
                )
            )

    rng = random.Random(20260920)
    sample = rng.sample(rows, 120)
    jobs = [(r["title"], translated) for r in sample for translated in (False, True)]
    expected = [
        parse_title(title, translate_languages=translated) for title, translated in jobs
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        actual = list(
            pool.map(
                lambda job: parse_title(job[0], translate_languages=job[1]),
                jobs,
            )
        )
    concurrent_errors = sum(a != b for a, b in zip(actual, expected))
    for result in actual:
        result["audio_languages"].clear()
        result.get("subtitle_languages", []).clear()
    isolation_errors = sum(
        parse_title(t, translate_languages=tr) != reference
        for (t, tr), reference in zip(jobs, expected)
    )
    cli_errors = []
    title = "Example.2024.1080p.VFQ.VOSTFR.DTS-HD.MA.7.1.4"
    for translated in (False, True):
        command = [
            sys.executable,
            "-m",
            "PTT.cli",
            "parse",
            title,
        ] + (["--translate-languages"] if translated else [])
        response = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", timeout=15
        )
        if response.returncode or json.loads(response.stdout) != parse_title(
            title, translate_languages=translated
        ):
            cli_errors.append(dict(translated=translated))
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "PTT").glob("*.py")
    }
    summary = dict(
        cases=len(rows),
        unique_titles=len({r["title"] for r in rows}),
        failures=dict(Counter(r["kind"] for r in failures)),
        semantic_groups=dict(
            Counter(r["group"] for r in failures if r["kind"] == "semantic")
        ),
        concurrent_checks=len(jobs),
        concurrent_errors=concurrent_errors,
        mutation_checks=len(jobs),
        isolation_errors=isolation_errors,
        cli_checks=2,
        cli_errors=cli_errors,
        source_sha256=before,
    )
    args.output.write_text(
        json.dumps(
            dict(summary=summary, failures=failures, cases=rows, results=results),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return bool(failures or concurrent_errors or isolation_errors or cli_errors)


if __name__ == "__main__":
    sys.exit(main())
