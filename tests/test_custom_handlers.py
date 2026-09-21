import pytest
import regex

from PTT import parse_title
from PTT.handlers import add_defaults
from PTT.parse import LANGUAGES_TRANSLATION_TABLE, Parser, translate_langs
from PTT.transformers import uniq_concat, value


@pytest.mark.parametrize("marker", ["ENGLISH", "VFQ", "MULTI"])
@pytest.mark.parametrize("forced,expected", [(["fr"], ["fr-FR"]), (["ja"], ["ja-JP"]), ([], [])])
@pytest.mark.parametrize("remove", [False, True])
def test_custom_language_value_overrides_detection(marker, forced, expected, remove):
    original = list(forced)
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile(marker), uniq_concat(value("en")), {"value": forced, "remove": remove})
    result = parser.parse(f"Example.2024.1080p.{marker}")
    assert result["audio_languages"] == expected
    assert forced == original


@pytest.mark.parametrize("field,marker,forced", [("audio", "DTS-HD.MA", ["FLAC"]), ("channels", "7.1.4", ["2.0"]), ("hdr", "HDR10+", ["HDR"]), ("quality", "DTS-HD.MA", "HDTV")])
def test_custom_value_survives_technical_refinement(field, marker, forced):
    parser = Parser()
    parser.add_handler("resolution", regex.compile("1080p"), value("1080p"))
    parser.add_handler(field, regex.compile(regex.escape(marker)), value(forced), {"value": forced})
    assert parser.parse(f"Example.2024.1080p.{marker}")[field] == forced


def test_later_handler_can_extend_a_custom_value():
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("ENGLISH"), uniq_concat(value("en")), {"value": ["fr"]})
    parser.add_handler("audio_languages", regex.compile("JAPANESE"), uniq_concat(value("ja")), {"skipIfAlreadyFound": False})
    assert parser.parse("Example.2024.1080p.ENGLISH.JAPANESE")["audio_languages"] == ["fr-FR", "ja-JP"]


def test_nonmatching_override_does_not_block_regular_detection():
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("CUSTOM"), uniq_concat(value("en")), {"value": []})
    add_defaults(parser)
    title = "Example.2024.1080p.JAPANESE.VOSTFR"
    assert parser.parse(title) == parse_title(title)


def test_last_custom_value_replaces_an_earlier_override():
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("ENGLISH"), uniq_concat(value("en")), {"value": ["fr"]})
    parser.add_handler("audio_languages", regex.compile("JAPANESE"), uniq_concat(value("ja")), {"value": ["de"], "skipIfAlreadyFound": False})
    assert parser.parse("Example.2024.1080p.ENGLISH.JAPANESE")["audio_languages"] == ["de-DE"]


def test_skipped_override_does_not_replace_an_accepted_value():
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("ENGLISH"), uniq_concat(value("en")))
    parser.add_handler("audio_languages", regex.compile("JAPANESE"), uniq_concat(value("ja")), {"value": ["fr"]})
    assert parser.parse("Example.2024.1080p.ENGLISH.JAPANESE")["audio_languages"] == ["en-US"]


def test_forced_value_does_not_repeat_the_transformer_for_recording():
    calls = []

    def transform(text):
        calls.append(text)
        return ["en"]

    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("ENGLISH"), transform, {"value": ["fr"]})
    assert parser.parse("Example.ENGLISH.ENGLISH")["audio_languages"] == ["fr-FR"]
    assert calls == ["ENGLISH"]


def test_custom_value_is_translated_and_does_not_leak_between_calls():
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("CUSTOM"), uniq_concat(value("en")), {"value": ["fr-CA"]})
    add_defaults(parser)
    assert parser.parse("Example.2024.CUSTOM", True)["audio_languages"] == ["French (Canada)"]
    assert parser.parse("Example.2024.JAPANESE")["audio_languages"] == ["ja-JP"]


@pytest.mark.parametrize("code,name", LANGUAGES_TRANSLATION_TABLE.items())
def test_translation_helper_keeps_legacy_short_codes(code, name):
    assert translate_langs([code]) == [name]


@pytest.mark.parametrize("code,expected", [("fr-CA", "French (Canada)"), ("fr-FR", "French (France)"), ("en-US", "English (United States)"), ("multi", "Multiple languages")])
def test_translation_helper_supports_fork_output(code, expected):
    assert translate_langs([code]) == [expected]


def test_translation_helper_keeps_unknown_codes_ignored():
    assert translate_langs(["not_a_language", "", "en"]) == ["English"]


@pytest.mark.parametrize("forced", [False, True])
@pytest.mark.parametrize("replacement", [[], ["ja"]])
@pytest.mark.parametrize("append_after", [False, True])
def test_replaced_languages_are_not_restored_by_metadata(forced, replacement, append_after):
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("ENGLISH"), uniq_concat(value("en")), {"value": ["fr"]} if forced else {})
    parser.add_handler("audio_languages", regex.compile("JAPANESE"), lambda text: list(replacement), {"skipIfAlreadyFound": False})
    if append_after:
        parser.add_handler("audio_languages", regex.compile("GERMAN"), uniq_concat(value("de")), {"skipIfAlreadyFound": False})
    result = parser.parse("Example.2024.1080p.ENGLISH.JAPANESE.GERMAN")
    assert result["audio_languages"] == (["ja-JP"] if replacement else []) + (["de-DE"] if append_after else [])


@pytest.mark.parametrize("in_place", [False, True])
def test_removed_language_stays_removed_after_partial_replacement(in_place):
    parser = Parser()
    calls = []
    parser.add_handler("audio_languages", regex.compile("ENGLISH"), uniq_concat(value("en")))
    parser.add_handler("audio_languages", regex.compile("FRENCH"), uniq_concat(value("fr")), {"skipIfAlreadyFound": False})

    def remove_english(text, existing):
        calls.append(text)
        if in_place:
            existing.remove("en")
            return existing
        return [code for code in existing if code != "en"]

    parser.add_handler("audio_languages", regex.compile("CUSTOM"), remove_english, {"skipIfAlreadyFound": False})
    assert parser.parse("Example.2024.1080p.ENGLISH.FRENCH.CUSTOM")["audio_languages"] == ["fr-FR"]
    assert calls == ["CUSTOM"]


def test_rejected_transformer_does_not_erase_languages():
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("ENGLISH"), uniq_concat(value("en")))
    parser.add_handler("audio_languages", regex.compile("JAPANESE"), lambda text: None, {"skipIfAlreadyFound": False})
    assert parser.parse("Example.2024.1080p.ENGLISH.JAPANESE")["audio_languages"] == ["en-US"]


@pytest.mark.parametrize("field,marker,initial,final", [("audio", "DTS-HD.MA", ["DTS Lossy"], ["FLAC"]), ("channels", "7.1.4", ["7.1"], ["2.0"]), ("hdr", "HDR10+", ["HDR10+"], ["HDR"])])
@pytest.mark.parametrize("clear", [False, True])
def test_replaced_technical_list_is_not_recreated_from_title(field, marker, initial, final, clear):
    parser = Parser()
    parser.add_handler("resolution", regex.compile("1080p"), value("1080p"))
    parser.add_handler(field, regex.compile(regex.escape(marker)), lambda text: list(initial))
    parser.add_handler(field, regex.compile("CUSTOM"), lambda text: [] if clear else list(final), {"skipIfAlreadyFound": False})
    assert parser.parse(f"Example.2024.1080p.{marker}.CUSTOM")[field] == ([] if clear else final)


def test_replacement_does_not_leak_to_later_parse():
    parser = Parser()
    parser.add_handler("audio_languages", regex.compile("ENGLISH"), uniq_concat(value("en")))
    parser.add_handler("audio_languages", regex.compile("CUSTOM"), lambda text: [], {"skipIfAlreadyFound": False})
    assert parser.parse("Example.2024.ENGLISH.CUSTOM")["audio_languages"] == []
    assert parser.parse("Example.2024.ENGLISH")["audio_languages"] == ["en-US"]
