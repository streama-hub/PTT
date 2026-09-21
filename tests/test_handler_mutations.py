import pytest
import regex

from PTT import Parser, add_defaults, parse_title
from PTT.transformers import uniq_concat, value


@pytest.mark.parametrize("before_defaults", [False, True])
@pytest.mark.parametrize("remove", [False, True])
def test_custom_subtitle_languages_are_preserved(before_defaults, remove):
    parser = Parser()
    if not before_defaults:
        add_defaults(parser)
    parser.add_handler("subtitle_languages", regex.compile("CUSTOM"), uniq_concat(value("fr")), {"remove": remove})
    if before_defaults:
        add_defaults(parser)
    result = parser.parse("Example.2024.1080p.CUSTOM")
    assert result["subtitle_languages"] == ["fr-FR"]
    assert result["audio_languages"] == []


@pytest.mark.parametrize("in_place", [False, True])
@pytest.mark.parametrize("field,marker,expected", [
    ("audio_languages", "JAPANESE", ["de-DE"]),
    ("audio", "DTS-HD.MA", ["FLAC"]),
    ("channels", "7.1.4", ["2.0"]),
    ("hdr", "HDR10+", ["SDR"]),
])
@pytest.mark.parametrize("clear", [False, True])
def test_callback_replacements_are_preserved(in_place, field, marker, expected, clear):
    parser = Parser()
    add_defaults(parser)
    replacement = [] if clear else expected

    def replace(context):
        if in_place:
            context["result"][field][:] = replacement
        else:
            context["result"][field] = list(replacement)

    parser.add_handler(replace)
    assert parser.parse(f"Example.2024.1080p.{marker}")[field] == replacement


def test_custom_subtitle_languages_merge_with_detected_subtitles():
    parser = Parser()
    parser.add_handler("subtitle_languages", regex.compile("CUSTOM"), uniq_concat(value("fr")))
    add_defaults(parser)
    result = parser.parse("Example.2024.1080p.CUSTOM.JAPANESE.ENGSUB")
    assert result["subtitle_languages"] == ["fr-FR", "en-US"]
    assert result["audio_languages"] == ["ja-JP"]


def test_callback_changes_do_not_leak_between_calls():
    parser = Parser()
    add_defaults(parser)

    def clear(context):
        if "CUSTOM" in context["title"]:
            context["result"]["audio_languages"] = []

    parser.add_handler(clear)
    assert parser.parse("Example.2024.1080p.JAPANESE.CUSTOM")["audio_languages"] == []
    title = "Example.2024.1080p.JAPANESE"
    assert parser.parse(title) == parse_title(title)


@pytest.mark.parametrize("field,marker", [("quality", "HDTV"), ("audio", "DTS-HD.MA"), ("hdr", "HDR10+")])
def test_callback_can_remove_a_field(field, marker):
    parser = Parser()
    add_defaults(parser)

    def remove(context):
        context["result"].pop(field, None)

    parser.add_handler(remove)
    assert field not in parser.parse(f"Example.2024.1080p.{marker}")


def test_regex_handler_can_append_after_a_callback_replacement():
    parser = Parser()
    add_defaults(parser)

    def replace(context):
        context["result"]["audio_languages"] = ["de"]

    parser.add_handler(replace)
    parser.add_handler("audio_languages", regex.compile("CUSTOM"), uniq_concat(value("fr")), {"skipIfAlreadyFound": False})
    assert parser.parse("Example.2024.1080p.JAPANESE.CUSTOM")["audio_languages"] == ["de-DE", "fr-FR"]


def test_custom_subtitles_are_translated_without_changing_audio():
    parser = Parser()
    parser.add_handler("subtitle_languages", regex.compile("CUSTOM"), uniq_concat(value("fr-CA")))
    add_defaults(parser)
    result = parser.parse("Example.2024.1080p.CUSTOM.JAPANESE", True)
    assert result["subtitle_languages"] == ["French (Canada)"]
    assert result["audio_languages"] == ["Japanese (Japan)"]


def test_callback_additions_preserve_native_refinement():
    parser = Parser()
    add_defaults(parser)

    def append(context):
        context["result"]["audio_languages"].append("de")

    parser.add_handler(append)
    result = parser.parse("Example.2024.1080p.VFQ")
    assert result["audio_languages"] == ["fr-CA", "de-DE"]


def test_later_handler_can_restore_a_removed_field():
    parser = Parser()
    add_defaults(parser)

    def remove(context):
        context["result"].pop("audio", None)

    parser.add_handler(remove)
    parser.add_handler("audio", regex.compile("CUSTOM"), value(["FLAC"]))
    assert parser.parse("Example.2024.1080p.DTS-HD.MA.CUSTOM")["audio"] == ["FLAC"]


@pytest.mark.parametrize("translate", [False, True])
@pytest.mark.parametrize("with_defaults", [False, True])
@pytest.mark.parametrize("remove_field", [False, True])
def test_callback_can_clear_or_remove_custom_subtitles(translate, with_defaults, remove_field):
    parser = Parser()
    parser.add_handler("subtitle_languages", regex.compile("FRENCH"), value(["fr"]))
    if with_defaults:
        add_defaults(parser)

    def remove(context):
        if remove_field:
            context["result"].pop("subtitle_languages", None)
        else:
            context["result"]["subtitle_languages"].clear()

    parser.add_handler(remove)
    result = parser.parse("Example.2024.1080p.FRENCH", translate)
    if remove_field:
        assert "subtitle_languages" not in result
    else:
        assert result["subtitle_languages"] == []
