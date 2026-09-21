import json
import subprocess
import sys

import pytest
import regex

from PTT import Parser, add_defaults, parse_title
from PTT.transformers import uniq_concat, value


@pytest.mark.parametrize("marker,audio,subtitles", [
    ("VFQ", ["fr-CA"], []),
    ("VFF", ["fr-FR"], []),
    ("JAPANESE VOSTFR", ["ja-JP"], ["fr-FR"]),
    ("MULTI", ["multi"], []),
    ("MULTi", ["multi"], []),
    ("multi", ["multi"], []),
    ("Multi-Subs", [], ["multi"]),
    ("MULTI-SUBS", [], ["multi"]),
    ("multi subs", [], ["multi"]),
    ("", [], []),
])
def test_audio_language_output_name(marker, audio, subtitles):
    result = parse_title(f"Example.E03.1080p {marker}")
    assert result["audio_languages"] == audio
    assert result["subtitle_languages"] == subtitles
    assert "languages" not in result
    assert result["seasons"] == []
    assert result["episodes"] == [3]


def test_audio_language_custom_handler():
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("CUSTOM"), uniq_concat(value("fr-CA")))
    add_defaults(parser)
    result = parser.parse("Example.2024.1080p.CUSTOM.VOSTFR")
    assert result["audio_languages"] == ["fr-CA"]
    assert result["subtitle_languages"] == ["fr-FR"]
    assert "languages" not in result


def test_cli_serializes_audio_language_name():
    title = "Example.2024.1080p.VFQ.VOSTFR"
    result = subprocess.run([sys.executable, "-m", "PTT.cli", "parse", title], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == parse_title(title)
