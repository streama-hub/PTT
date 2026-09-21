import pytest
import regex

from PTT import parse_title
from PTT.metadata import compile_language_patterns
from PTT.parse import LANGUAGES_TRANSLATION_TABLE


def test_language_patterns_are_reused():
    languages = tuple(LANGUAGES_TRANSLATION_TABLE.items())
    assert compile_language_patterns(languages) is compile_language_patterns(languages)


@pytest.mark.parametrize("code,name", LANGUAGES_TRANSLATION_TABLE.items())
def test_language_patterns_preserve_matches(code, name):
    pattern = dict(compile_language_patterns(tuple(LANGUAGES_TRANSLATION_TABLE.items())))[code]
    original = r"\b(?:" + regex.escape(name) + r"|" + code + r")\b"
    for title in (f"Example.2024.1080p.[Subs: {name} {code}]", f"[Audio {name.upper()}] Example S01E02", f"{name.lower()}.srt", f"x{name}x x{code}x"):
        expected = [(match.span(), match.group()) for match in regex.finditer(original, title, regex.IGNORECASE)]
        assert [(match.span(), match.group()) for match in pattern.finditer(title)] == expected


def test_language_patterns_preserve_table_order():
    languages = tuple(LANGUAGES_TRANSLATION_TABLE.items())
    assert [code for code, _ in compile_language_patterns(languages)] == list(LANGUAGES_TRANSLATION_TABLE)
    assert [code for code, _ in compile_language_patterns(languages[::-1])] == list(LANGUAGES_TRANSLATION_TABLE)[::-1]


def test_language_patterns_follow_table_updates(monkeypatch):
    languages = tuple(LANGUAGES_TRANSLATION_TABLE.items())
    original = compile_language_patterns(languages)
    monkeypatch.setitem(LANGUAGES_TRANSLATION_TABLE, "en", "EnglishCustom")
    updated = compile_language_patterns(tuple(LANGUAGES_TRANSLATION_TABLE.items()))
    assert updated is not original
    assert dict(updated)["en"].fullmatch("EnglishCustom")
    assert not dict(updated)["en"].fullmatch("English")
    assert parse_title("Example.2024.1080p.[Subs: EnglishCustom]")["subtitle_languages"] == ["en-US"]
    monkeypatch.setitem(LANGUAGES_TRANSLATION_TABLE, "en", "English")
    assert compile_language_patterns(tuple(LANGUAGES_TRANSLATION_TABLE.items())) is original
    assert parse_title("Example.2024.1080p.[Subs: English]")["subtitle_languages"] == ["en-US"]


def test_language_patterns_escape_names():
    pattern = dict(compile_language_patterns((("en", "English+Custom"),)))["en"]
    assert pattern.fullmatch("English+Custom")
    assert not pattern.fullmatch("EnglishCustom")
    assert pattern.fullmatch("en")


def test_language_pattern_cache_is_bounded():
    compile_language_patterns.cache_clear()
    for index in range(12):
        compile_language_patterns((("en", f"English{index}"),))
    assert compile_language_patterns.cache_info().currsize == 8
    compile_language_patterns.cache_clear()
