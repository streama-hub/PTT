import inspect
from typing import Any, Callable, Dict, List, Union

import regex

from .transformers import none

# Non-English characters range
NON_ENGLISH_CHARS = (
    "\u3040-\u30ff"  # Japanese characters
    "\u3400-\u4dbf"  # Chinese characters
    "\u4e00-\u9fff"  # Chinese characters
    "\uf900-\ufaff"  # CJK Compatibility Ideographs
    "\uff66-\uff9f"  # Halfwidth Katakana Japanese characters
    "\u0400-\u04ff"  # Cyrillic characters (Russian)
    "\u0600-\u06ff"  # Arabic characters
    "\u0750-\u077f"  # Arabic characters
    "\u0c80-\u0cff"  # Kannada characters
    "\u0d00-\u0d7f"  # Malayalam characters
    "\u0e00-\u0e7f"  # Thai characters
)

CURLY_BRACKETS = ["{", "}"]
SQUARE_BRACKETS = ["[", "]"]
PARENTHESES = ["(", ")"]
BRACKETS = [CURLY_BRACKETS, SQUARE_BRACKETS, PARENTHESES]

RUSSIAN_CAST_REGEX = regex.compile(r"\([^)]*[\u0400-\u04ff][^)]*\)$|(?<=\/.*)\(.*\)$")
ALT_TITLES_REGEX = regex.compile(rf"[^/|(]*[{NON_ENGLISH_CHARS}][^/|]*[/|]|[/|][^/|(]*[{NON_ENGLISH_CHARS}][^/|]*")
NOT_ONLY_NON_ENGLISH_REGEX = regex.compile(rf"(?<=[a-zA-Z][^{NON_ENGLISH_CHARS}]+)[{NON_ENGLISH_CHARS}].*[{NON_ENGLISH_CHARS}]|[{NON_ENGLISH_CHARS}].*[{NON_ENGLISH_CHARS}](?=[^{NON_ENGLISH_CHARS}]+[a-zA-Z])")
NOT_ALLOWED_SYMBOLS_AT_START_AND_END = regex.compile(rf"^[^\w{NON_ENGLISH_CHARS}#[【★]+|[ \-:/\\[|{{(#$&^]+$")
REMAINING_NOT_ALLOWED_SYMBOLS_AT_START_AND_END = regex.compile(rf"^[^\w{NON_ENGLISH_CHARS}#]+|]$")
REDUNDANT_SYMBOLS_AT_END = regex.compile(r"[ \-:./\\]+$")
EMPTY_BRACKETS_REGEX = regex.compile(r"\(\s*\)|\[\s*\]|\{\s*\}")
PARANTHESES_WITHOUT_CONTENT = regex.compile(r"\(\W*\)|\[\W*\]|\{\W*\}")
MOVIE_REGEX = regex.compile(r"[[(]movie[)\]]", flags=regex.IGNORECASE)
STAR_REGEX_1 = regex.compile(r"^[[【★].*[\]】★][ .]?(.+)")
STAR_REGEX_2 = regex.compile(r"(.+)[ .]?[[【★].*[\]】★]$")
MP3_REGEX = regex.compile(r"\bmp3$")
SPACING_REGEX = regex.compile(r"\s+")
SPECIAL_CHAR_SPACING = regex.compile(r"[\-\+\_\{\}\[\]]\W{2,}")
SUB_PATTERN = regex.compile(r"_+")

BEFORE_TITLE_MATCH_REGEX = regex.compile(r"^\[([^[\]]+)]")

DEBUG_HANDLER = False


def extend_options(options: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Extend the options dictionary with default values.

    :param options: The original options dictionary.
    :return: The extended options dictionary.
    """
    default_options = {
        "skipIfAlreadyFound": True,
        "skipFromTitle": False,
        "skipIfFirst": False,
        "remove": False,
    }
    for key, value in default_options.items():
        options.setdefault(key, value)
    return options


def create_handler_from_regexp(name: str, reg_exp: regex.Pattern, transformer: Callable, options: Dict[str, Any]) -> Callable:
    """
    Create a handler function from a regular expression pattern.

    :param name: The name of the handler.
    :param reg_exp: The regular expression pattern.
    :param transformer: The transformer function to process the match.
    :param options: Additional options for the handler.
    :return: The handler function.
    """

    def handler(context: Dict[str, Any]) -> Union[Dict[str, Any], None]:
        title = context["title"]
        result = context["result"]
        matched = context["matched"]

        if name in result and options.get("skipIfAlreadyFound", False):
            return None
        if DEBUG_HANDLER is True or (isinstance(DEBUG_HANDLER, str) and DEBUG_HANDLER in name):
            print(name, "Try to match " + title, "To " + reg_exp.pattern)
        match = reg_exp.search(title)
        if DEBUG_HANDLER is True or (isinstance(DEBUG_HANDLER, str) and DEBUG_HANDLER in name):
            print("Matched " + str(match))
        if match:
            raw_match = match.group(0)
            clean_match = match.group(1) if len(match.groups()) >= 1 else raw_match
            sig = inspect.signature(transformer)
            param_count = len(sig.parameters)
            previous_values = list(result[name]) if isinstance(result.get(name), list) else []
            transformed = transformer(clean_match or raw_match, *([result.get(name)] if param_count > 1 else []))
            if isinstance(transformed, str):
                transformed = transformed.strip()

            before_title_match = BEFORE_TITLE_MATCH_REGEX.match(title)
            is_before_title = before_title_match is not None and raw_match in before_title_match.group(1)

            other_matches = {k: v for k, v in matched.items() if k != name}
            is_skip_if_first = options.get("skipIfFirst", False) and other_matches and all(match.start() < other_matches[k]["match_index"] for k in other_matches)
            replacement = options.get("value", transformed)
            replaces_values = isinstance(replacement, list) and any(item not in replacement for item in previous_values)

            if transformed is not None and not replaces_values and context.get("details") is not None and name in context["details"].fields and (not is_skip_if_first or name == "audio_languages"):
                for item in reg_exp.finditer(title):
                    if options.get("skipIfFirst", False) and other_matches and all(item.start() < other_matches[k]["match_index"] for k in other_matches):
                        continue
                    text = item.group(1) if item.groups() else item.group()
                    emitted = options["value"] if "value" in options else transformer(text or item.group(), *([[]] if param_count > 1 else []))
                    context["details"].record(name, item.span(), emitted, context["positions"])
            if transformed is not None and not is_skip_if_first:
                matched[name] = matched.get(name, {"raw_match": raw_match, "match_index": match.start()})
                result[name] = options.get("value", transformed)
                if context.get("details") is not None:
                    if replaces_values:
                        context["details"].replacements.add(name)
                    if "value" in options or name in context["details"].replacements:
                        context["details"].overrides.add(name)
                    else:
                        context["details"].overrides.discard(name)
                return {"raw_match": raw_match, "match_index": match.start(), "remove": options.get("remove", False), "skip_from_title": is_before_title or options.get("skipFromTitle", False)}
        return None

    handler.__name__ = name
    setattr(handler, "handler_name", name)
    setattr(handler, "records_matches", True)
    return handler


def clean_title(raw_title: str) -> str:
    """
    Clean up a title string by removing unwanted characters and patterns.

    :param raw_title: The raw title string.
    :return: The cleaned title string.
    """
    cleaned_title = raw_title
    cleaned_title = cleaned_title.replace("_", " ")
    cleaned_title = MOVIE_REGEX.sub("", cleaned_title)
    cleaned_title = NOT_ALLOWED_SYMBOLS_AT_START_AND_END.sub("", cleaned_title)
    cleaned_title = RUSSIAN_CAST_REGEX.sub("", cleaned_title)
    cleaned_title = STAR_REGEX_1.sub(r"\1", cleaned_title)
    cleaned_title = STAR_REGEX_2.sub(r"\1", cleaned_title)
    cleaned_title = ALT_TITLES_REGEX.sub("", cleaned_title)
    cleaned_title = NOT_ONLY_NON_ENGLISH_REGEX.sub("", cleaned_title)
    cleaned_title = REMAINING_NOT_ALLOWED_SYMBOLS_AT_START_AND_END.sub("", cleaned_title)
    cleaned_title = EMPTY_BRACKETS_REGEX.sub("", cleaned_title)
    cleaned_title = MP3_REGEX.sub("", cleaned_title)
    cleaned_title = PARANTHESES_WITHOUT_CONTENT.sub("", cleaned_title)
    cleaned_title = SPECIAL_CHAR_SPACING.sub("", cleaned_title)

    # Remove brackets if only one is present
    for open_bracket, close_bracket in BRACKETS:
        if cleaned_title.count(open_bracket) != cleaned_title.count(close_bracket):
            cleaned_title = cleaned_title.replace(open_bracket, "").replace(close_bracket, "")

    if " " not in cleaned_title and "." in cleaned_title:
        cleaned_title = regex.sub(r"\.", " ", cleaned_title)

    cleaned_title = REDUNDANT_SYMBOLS_AT_END.sub("", cleaned_title)
    cleaned_title = SPACING_REGEX.sub(" ", cleaned_title)
    cleaned_title = cleaned_title.strip()
    return cleaned_title


LANGUAGES_TRANSLATION_TABLE = {
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
    "ru": "Russian",
    "ar": "Arabic",
    "pt": "Portuguese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ko": "Korean",
    "hi": "Hindi",
    "bn": "Bengali",
    "pa": "Punjabi",
    "mr": "Marathi",
    "gu": "Gujarati",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "tr": "Turkish",
    "he": "Hebrew",
    "fa": "Persian",
    "uk": "Ukrainian",
    "el": "Greek",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "et": "Estonian",
    "pl": "Polish",
    "cs": "Czech",
    "sk": "Slovak",
    "hu": "Hungarian",
    "ro": "Romanian",
    "bg": "Bulgarian",
    "sr": "Serbian",
    "hr": "Croatian",
    "sl": "Slovenian",
    "nl": "Dutch",
    "da": "Danish",
    "fi": "Finnish",
    "sv": "Swedish",
    "no": "Norwegian",
    "ms": "Malay",
    "la": "Latino",
}


def translate_langs(langs: List[str]) -> List[str]:
    """Translate language codes and regional tags to their corresponding display names."""
    from langcodes import Language, tag_is_valid

    translated = []
    for code in langs:
        if code in LANGUAGES_TRANSLATION_TABLE:
            translated.append(LANGUAGES_TRANSLATION_TABLE[code])
        elif code == "multi":
            translated.append("Multiple languages")
        elif "-" in code and tag_is_valid(code):
            translated.append(Language.get(code).display_name("en"))
    return translated


class Parser:
    """
    A parser that can parse release titles using a set of handlers.

    Each handler receives a context containing the current title, results and matches. The parser runs all handlers
    in order, accumulates their results and returns the parsed metadata with the cleaned title.

    The parser can be extended with new handlers using the add_handler method. The handler can be a function or a
    regular expression pattern. If a regular expression pattern is used, the parser will use the first group as the
    match to be transformed by the transformer function.

    Example:
        >>> import regex
        >>> from PTT import Parser
        >>> parser = Parser()
        >>> parser.add_handler("seasons", regex.compile(r"Season (\\d+)"), lambda value: [int(value)])
        >>> parser.add_handler("episodes", regex.compile(r"Episode (\\d+)"), lambda value: [int(value)])
        >>> parser.add_handler("audio_languages", regex.compile(r"English"), lambda value: ["en"])
        >>> result = parser.parse("The Simpsons Season 1 Episode 1 English")
        >>> result["title"], result["seasons"], result["episodes"], result["audio_languages"]
        ('The Simpsons', [1], [1], ['en-US'])
    """

    def __init__(self):
        self.handlers: List[Callable] = []

    def add_handler(self, handler_name: str, handler: Union[Callable, regex.Pattern, None] = None, transformer: Union[Callable, None] = None, options: Union[Dict[str, Any], None] = None):
        """
        Add a handler to the parser. The handler can be a function or a regular expression pattern.

        :param handler_name: The name of the handler.
        :param handler: The handler function or regex pattern.
        :param transformer: The transformer function to process the match.
        :param options: Additional options for the handler.
        """
        if handler is None and callable(handler_name):
            handler = handler_name
            setattr(handler, "handler_name", getattr(handler_name, "__name__", "unknown"))
        elif isinstance(handler_name, str) and isinstance(handler, regex.Pattern):
            transformer = transformer if callable(transformer) else none
            options = extend_options(options if isinstance(options, dict) else {})
            handler = create_handler_from_regexp(handler_name, handler, transformer, options)
        elif isinstance(handler_name, str) and callable(handler):
            setattr(handler, "handler_name", handler_name)
        else:
            raise ValueError(f"Handler for {handler_name} should be either a regex pattern or a function. Got {type(handler)}")

        self.handlers.append(handler)

    def parse(self, title: str, translate_languages: bool = False) -> Dict[str, Any]:
        """
        Parse a release title and return the parsed data as a dictionary.

        :param title: The release title to parse.
        :param translate_languages: Whether to translate regional language tags to display names.
        :return: A dictionary containing the parsed data.
        """
        from .metadata import MatchDetails

        title = SUB_PATTERN.sub(" ", title)
        details = MatchDetails(title)
        positions = list(range(len(title)))
        result: Dict[str, Any] = {}
        matched: Dict[str, Any] = {}
        end_of_title = len(title)

        for handler in self.handlers:
            context = {"title": title, "result": result, "matched": matched, "details": details, "positions": positions}
            records_matches = getattr(handler, "records_matches", False)
            previous = {field: list(value) if isinstance(value, list) else value for field, value in result.items() if field in details.refined_fields} if not records_matches else {}
            match_result = handler(context)
            if not records_matches:
                details.track_changes(previous, result)

            if DEBUG_HANDLER is True or (isinstance(DEBUG_HANDLER, str) and hasattr(handler, "handler_name") and DEBUG_HANDLER in getattr(handler, "handler_name", "")):
                print(getattr(handler, "handler_name", "unknown"), match_result, title)

            if match_result is None:
                continue

            match_index = match_result.get("match_index")
            raw_match = match_result.get("raw_match", "")
            remove = match_result.get("remove", False)
            skip_from_title = match_result.get("skip_from_title", False)

            if remove:
                title = title[:match_index] + title[match_index + len(raw_match) :]
                del positions[match_index : match_index + len(raw_match)]
            if not skip_from_title and match_index and 1 < match_index < end_of_title:
                end_of_title = match_index
            if remove and skip_from_title and match_index < end_of_title:
                end_of_title -= len(raw_match)

        result.setdefault("episodes", [])
        result.setdefault("seasons", [])
        result.setdefault("audio_languages", [])

        title_positions = positions[:end_of_title]
        details.title_end = title_positions[-1] + 1 if title_positions else 0
        details.apply(result, translate_languages)

        # Clean the title up to end_of_title before further processing.
        title = title[:end_of_title]
        result["title"] = clean_title(title)
        return result
