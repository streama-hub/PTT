from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import regex
from langcodes import Language, tag_is_valid

CHANNEL_LAYOUT_PATTERN = r"([1-9]\d?[. -][012][. -][1-9]\d?)(?:ch)?(?!\w|[.]\d(?!\d{2,3}[pi]\b))"
NON_CHANNEL_UNIT_REGEX = regex.compile(r"[ .-]*(?:[KMGT]i?[BO]|FPS|K?BPS)\b", regex.IGNORECASE)
TECHNICAL_PATTERNS = [
    ("audio", r"DTS[ .:-]*HD[ .-]*MA(?:STER)?(?:[ .-]*AUDIO)?|DTS[ .-]*MA", "DTS-HD MA"),
    ("audio", r"DTS[ .:-]*HD[ .-]*(?:HRA?|HIGH[ .-]*RESOLUTION(?:[ .-]*AUDIO)?)", "DTS-HD HRA"),
    ("audio", r"DTS[ .:-]*X", "DTS-X"),
    ("audio", r"DTS[ .:-]*HD", "DTS-HD"),
    ("audio", r"HE[ .-]*AAC[ .-]*V2", "HE-AACv2"),
    ("audio", r"HE[ .-]*AAC", "HE-AAC"),
    ("audio", r"TRUE[ .-]*HD(?=\d[. ]\d)", "TrueHD"),
    ("audio", r"AAC(?=\d[. ]\d)", "AAC"),
    ("audio", r"DTS(?=\d[. ]\d)", "DTS Lossy"),
    ("channels", r"(?<!\b\d+[. -])" + CHANNEL_LAYOUT_PATTERN, None),
    ("hdr", r"HDR10(?:\+|[ .-]*PLUS)", "HDR10+"),
    ("hdr", r"HDR10", "HDR10"),
    ("hdr", r"HLG", "HLG"),
    ("dolby_vision_profiles", r"(?:DV|DOVI|DOLBY[ .-]*VISION)[ .-]*(?:PROFILE|PROFIL|P)[ .-]*(\d{1,2}(?:\.\d{1,2})?)(?!\.\d(?!\d{2,3}[pi]\b))", None),
]
TECHNICAL_PATTERNS = [(field, regex.compile((r"(?<!\d)" if field == "channels" else r"(?<!\w)") + r"(?:" + pattern + r")(?=$|\W|\d[. ]\d)", regex.IGNORECASE), value) for field, pattern, value in TECHNICAL_PATTERNS]
LANGUAGE_ROLE_REGEX = regex.compile(r"\b(audio|dub(?:bed|lado)?|subs?(?:titles?)?|sdh|forced|leg(?:endado|endas?)?|undertekst)\b", regex.IGNORECASE)
AUDIO_MARKER_ROLE_REGEX = regex.compile(LANGUAGE_ROLE_REGEX.pattern + r"(?=[ .-]*[:\[({])|(?<!\bmulti(?:ple)?[ .-]*)" + LANGUAGE_ROLE_REGEX.pattern, regex.IGNORECASE)
SUBTITLE_FILE_REGEX = regex.compile(r"\.(?:srt|ass|ssa|vtt|sub|idx|smi|ttxt)\s*$", regex.IGNORECASE)
MULTI_SUBTITLE_PATTERN = r"MULTI(?:PLE)?[ .-]*SUB(?:S|TITLES?|BED)?|MSUB"
LANGUAGE_MARKER_REGEX = regex.compile(r"\b(VFQ|VFF|TRUEFRENCH|SUBFRENCH|FRENCH|VOSTFR|VOSTA|ENGSUB|ESUBS?|" + MULTI_SUBTITLE_PATTERN + r"|MULTI(?:PLE)?[ .-]*AUDIO|MULTI)\b", regex.IGNORECASE)
REGIONAL_LANGUAGE_REGEX = regex.compile(r"(?<![\w-])([a-z]{2,3}-(?:[a-z]{4}-)?(?:[a-z]{2}|\d{3}))(?![\w-])", regex.IGNORECASE)


@lru_cache(maxsize=8)
def compile_language_patterns(languages: Tuple[Tuple[str, str], ...]) -> Tuple[Tuple[str, regex.Pattern], ...]:
    """Reuse language patterns while preserving the translation table's contents and order."""
    return tuple((code, regex.compile(r"\b(?:" + regex.escape(name) + r"|" + code + r")\b", regex.IGNORECASE)) for code, name in languages)


@lru_cache(maxsize=256)
def transform_language(code: str) -> str:
    """
    Convert a language code to a regional tag, preserving explicit regions and scripts.

    :param code: The language code or the multi marker.
    :return: The regional tag using CLDR defaults where needed, or multi unchanged.
    """
    if code == "multi":
        return code
    if code == "la":
        return "es-419"
    language = Language.get(code)
    if language.territory:
        return language.to_tag()
    maximized = language.maximize()
    return Language.make(language=language.language, script=language.script, territory=maximized.territory).to_tag()


def unique(values: Iterable[str]) -> List[str]:
    """
    Remove duplicate values while preserving their order.

    :param values: The values to deduplicate.
    :return: A list containing the first occurrence of each value.
    """
    return list(dict.fromkeys(values))


def overlaps(left: Tuple[int, int], right: Tuple[int, int]) -> bool:
    """
    Check whether two match spans overlap.

    :param left: The first span, with an exclusive end position.
    :param right: The second span, with an exclusive end position.
    :return: True if the spans share at least one position.
    """
    return left[0] < right[1] and right[0] < left[1]


class MatchDetails:
    """
    Track metadata matches in the original title before handlers remove text.

    Recorded positions separate audio and subtitle languages and refine technical values
    without changing the title boundaries selected by the parser.
    """

    fields = {"audio_languages", "audio", "channels", "hdr", "quality", "year", "resolution", "seasons", "episodes", "group", "site", "subbed", "dubbed"}
    refined_fields = {"audio_languages", "subtitle_languages", "audio", "channels", "hdr", "dolby_vision_profiles", "quality", "extended", "remastered"}

    def __init__(self, title: str):
        self.title = title
        self.matches: List[Tuple[str, Tuple[int, int], Any]] = []
        self.overrides: Set[str] = set()
        self.replacements: Set[str] = set()
        self.title_end = 0
        self.blocks: List[Tuple[int, int]] = []
        stack = []
        for index, char in enumerate(title):
            if char in "[({":
                stack.append((char, index))
            elif char in "])}" and stack and "[({".index(stack[-1][0]) == "])}".index(char):
                self.blocks.append((stack.pop()[1], index))
        self.blocks.extend((index, len(title)) for _, index in stack)
        self.blocks.sort(reverse=True)

    def track_changes(self, previous: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Preserve callback removals and replacements through metadata refinement."""
        for field in (previous.keys() | result.keys()) & self.refined_fields:
            if field in previous and field in result and previous[field] == result[field]:
                continue
            current = result.get(field)
            if isinstance(current, list) and current and all(value in current for value in previous.get(field, [])):
                continue
            self.replacements.add(field)
            self.overrides.add(field)

    def record(self, field: str, span: Tuple[int, int], values: Any, positions: List[int]) -> None:
        """
        Record a handler match using positions from the original title.

        :param field: The result field associated with the match.
        :param span: The match span in the remaining title.
        :param values: The transformed value or list of values.
        :param positions: The original position of each remaining character.
        """
        if not positions or span[0] == span[1]:
            return
        if field not in self.fields:
            return
        start, end = positions[span[0]], positions[span[1] - 1] + 1
        values = values if isinstance(values, list) else [values]
        for value in values:
            if value is not None:
                self.matches.append((field, (start, end), value))

    def is_metadata_position(self, span: Tuple[int, int]) -> bool:
        """Check whether a span belongs to metadata rather than an unlabelled title or group."""
        if any(field in {"audio_languages", "audio", "channels", "hdr", "subbed", "dubbed"} and overlaps(span, location) for field, location, _ in self.matches):
            return True
        if self.is_labelled_language(span):
            return True
        if any(field in {"group", "site"} and location[0] <= span[0] and span[1] <= location[1] for field, location, _ in self.matches):
            return False
        if any(field in {"year", "resolution", "seasons", "episodes"} and location[1] <= span[0] for field, location, _ in self.matches):
            return True
        return False

    def get_context_text(self, start: int, end: int) -> str:
        """Mask nested blocks and their language-list labels without shifting positions."""
        text = list(self.title[start:end])
        for left, right in self.blocks:
            if start <= right < end:
                if left >= start:
                    label = regex.search(LANGUAGE_ROLE_REGEX.pattern + r"[ .,:-]*$", self.title[start:left], regex.IGNORECASE)
                    if label and self.is_language_list(start + label.start() + len(label.group(1))):
                        left = start + label.start()
                left = max(start, left)
                text[left - start : right - start + 1] = " " * (right - left + 1)
        return "".join(text)

    def is_language_list(self, start: int) -> bool:
        """Check whether a bracketed or colon-prefixed language list starts after the given position."""
        opening = regex.match(r"(?:[ .,:-]*[\[({]|[ .-]*:)\s*", self.title[start:])
        if not opening:
            return False
        start += opening.end()
        if any(field == "audio_languages" and span[0] == start for field, span, _ in self.matches):
            return True
        from .parse import LANGUAGES_TRANSLATION_TABLE

        return any(regex.match(r"(?:" + regex.escape(name) + "|" + code + r")\b", self.title[start:], regex.IGNORECASE) for code, name in LANGUAGES_TRANSLATION_TABLE.items())

    def is_labelled_language(self, span: Tuple[int, int]) -> bool:
        """Check for an explicit language role or a bounded subtitle annotation in the containing block."""
        for start, end in self.blocks:
            if start < span[0] and span[1] <= end:
                prefix = self.get_context_text(start + 1, span[0])
                suffix = self.title[span[1] : end]
                if LANGUAGE_ROLE_REGEX.search(prefix) or regex.fullmatch(r"[ .,:-]*(?:subs?(?:titles?)?|SDH|FORCED)[ .,:-]*", suffix, regex.IGNORECASE):
                    return True
                if regex.fullmatch(r"[ .,:-]*", prefix) and self.has_subtitle_annotation(span[1], end):
                    return True
        return False

    def has_subtitle_annotation(self, end: int, limit: Optional[int] = None) -> bool:
        """
        Check for an SDH or Forced annotation immediately after a language match.

        :param end: The position after the language match.
        :param limit: An optional enclosing block boundary, excluding unrelated trailing text.
        :return: True if a matching annotation is found within the boundary.
        """
        suffix = self.title[end:limit]
        annotation = regex.match(r"[ .,:-]*(?:sdh|forced)\b", suffix, regex.IGNORECASE)
        if annotation and (limit is None or regex.fullmatch(r"[ .,:-]*", suffix[annotation.end() :])):
            return True
        for left, right in self.blocks:
            if end <= left and right < (len(self.title) if limit is None else limit) and regex.fullmatch(r"[ .,:-]*", self.title[end:left]):
                if limit is not None and not regex.fullmatch(r"[ .,:-]*", self.title[right + 1 : limit]):
                    continue
                if regex.fullmatch(r"\s*(?:sdh|forced)\s*", self.title[left + 1 : right], regex.IGNORECASE):
                    return True
        return False

    def get_language_role(self, span: Tuple[int, int]) -> str:
        """
        Determine whether a language match describes audio or subtitles.

        :param span: The language match span in the original title.
        :return: The audio_languages or subtitle_languages result field.
        """
        if SUBTITLE_FILE_REGEX.search(self.title):
            return "subtitle_languages"
        for left, right in self.blocks:
            if left < span[0] < right:
                span = (span[0], min(span[1], right))
                break
        text = self.title[span[0] : span[1]]
        role_regex = AUDIO_MARKER_ROLE_REGEX if regex.fullmatch(r"VOF|VF[FQIB2]?|TRUEFRENCH|MULTI(?:PLE)?(?:[ .-]*AUDIO)?", text, regex.IGNORECASE) else LANGUAGE_ROLE_REGEX
        if regex.fullmatch(MULTI_SUBTITLE_PATTERN, text, regex.IGNORECASE):
            return "subtitle_languages"
        opens_list = self.is_language_list(span[1])
        list_label = opens_list and regex.search(r"\bsubs?(?:titles?)?\s*$", text, regex.IGNORECASE)
        if not list_label and regex.search(r"vost|sub|undertekst|\b(?:sdh|forced|leg(?:endado|endas?)?)\b", text, regex.IGNORECASE):
            return "subtitle_languages"
        if self.has_subtitle_annotation(span[1]):
            return "subtitle_languages"
        for left, right in self.blocks:
            if left < span[0] and span[1] <= right:
                labels = list(role_regex.finditer(self.get_context_text(left + 1, span[0])))
                if labels:
                    return "audio_languages" if regex.match(r"audio|dub", labels[-1].group(), regex.IGNORECASE) else "subtitle_languages"
        start = 0
        if not self.is_labelled_language(span):
            if span[0] < self.title_end:
                return "audio_languages"
            start = max(start, self.title_end)
            for field, location, _ in self.matches:
                if field in {"year", "resolution", "seasons", "episodes"} and location[1] <= span[0]:
                    start = max(start, location[1])
        labels = list(role_regex.finditer(self.get_context_text(start, span[0])))
        if labels:
            containing = [left for left, right in self.blocks if left < span[0] and span[1] <= right]
            if not containing or regex.fullmatch(r"[ .,:-]*", self.title[start + labels[-1].end() : min(containing)]):
                return "audio_languages" if regex.match(r"audio|dub", labels[-1].group(), regex.IGNORECASE) else "subtitle_languages"
        following = regex.match(r"[ .,:-]*(subs?(?:titles?)?|sdh|forced|undertekst)\b", self.title[span[1] :], regex.IGNORECASE)
        if following and not self.is_language_list(span[1] + following.end()):
            return "subtitle_languages"
        return "audio_languages"

    def process_languages(self, result: Dict[str, Any], refinements: List[Tuple[str, Tuple[int, int], str]]) -> None:
        """
        Merge recorded and explicit languages into separate regional audio and subtitle lists.

        :param result: The parser result to update in place.
        :param refinements: Technical matches excluded from additional language detection.
        """
        detected = [(span, code) for field, span, code in self.matches if field == "audio_languages"]
        explicit = []
        for match in LANGUAGE_MARKER_REGEX.finditer(self.title):
            if not self.is_metadata_position(match.span()):
                continue
            marker = match.group().upper()
            if marker == "FRENCH" and not self.is_labelled_language(match.span()):
                if match.start() < self.title_end or regex.search(r"\bsubbed\b", self.title, regex.IGNORECASE):
                    continue
                if any(left < match.start() and right == len(self.title) for left, right in self.blocks):
                    continue
            if marker == "VFQ":
                code = "fr-CA"
            elif marker in {"VFF", "TRUEFRENCH"}:
                code = "fr-FR"
            elif marker in {"VOSTFR", "SUBFRENCH", "FRENCH"}:
                code = "fr"
            elif marker in {"VOSTA", "ENGSUB", "ESUB", "ESUBS"}:
                code = "en"
            else:
                code = "multi"
            explicit.append((match.span(), code))
        from .parse import LANGUAGES_TRANSLATION_TABLE

        for match in REGIONAL_LANGUAGE_REGEX.finditer(self.title):
            code = match.group()
            if not tag_is_valid(code) or Language.get(code).language not in LANGUAGES_TRANSLATION_TABLE:
                continue
            if self.is_metadata_position(match.span()):
                explicit.append((match.span(), code))
        for code, pattern in compile_language_patterns(tuple(LANGUAGES_TRANSLATION_TABLE.items())):
            for match in pattern.finditer(self.title):
                if any(overlaps(match.span(), span) for _, span, _ in refinements):
                    continue
                if (self.get_language_role(match.span()) == "subtitle_languages" or self.is_labelled_language(match.span())) and self.is_metadata_position(match.span()):
                    if not any(overlaps(match.span(), span) for span, _ in detected + explicit):
                        explicit.append((match.span(), code))
        entries = [(span, code) for span, code in detected if not any(overlaps(span, location) for location, _ in explicit)] + explicit
        output = {"audio_languages": [], "subtitle_languages": list(result.get("subtitle_languages", []))}
        for span, code in sorted(entries, key=lambda item: item[0][0]):
            text = self.title[span[0] : span[1]]
            if code == "zh" and regex.search(r"\bCHT\b|hant|traditional", text, regex.IGNORECASE):
                code = "zh-Hant"
            elif code == "zh" and regex.search(r"\bCHS\b|hans|simplified", text, regex.IGNORECASE):
                code = "zh-Hans"
            elif code == "pt" and regex.search(r"\bBR\b|brazil", text, regex.IGNORECASE):
                code = "pt-BR"
            output[self.get_language_role(span)].append(code)
        recorded = {code for _, code in detected}
        recorded.update(Language.get(code).language if code != "multi" else code for _, code in explicit)
        for code in result.get("audio_languages", []):
            if code not in recorded:
                output["subtitle_languages" if SUBTITLE_FILE_REGEX.search(self.title) else "audio_languages"].append(code)
        for field, values in output.items():
            explicit_languages = {Language.get(code).language for code in values if code != "multi" and "-" in code}
            values = [code for code in values if code == "multi" or "-" in code or Language.get(code).language not in explicit_languages]
            result[field] = unique(transform_language(code) for code in values)

    def find_technical_matches(self) -> List[Tuple[str, Tuple[int, int], str]]:
        """Find detailed codec, channel and HDR matches with their original positions."""
        refinements = []
        for field, pattern, value in TECHNICAL_PATTERNS:
            for match in pattern.finditer(self.title):
                if not self.is_metadata_position(match.span()):
                    continue
                if any(field == other and overlaps(match.span(), span) for other, span, _ in refinements):
                    continue
                if field == "channels" and NON_CHANNEL_UNIT_REGEX.match(self.title, match.end()):
                    continue
                if field == "channels" and match.start() and self.title[match.start() - 1].isalnum():
                    if not any(name == "audio" and span[1] == match.start() for name, span, _ in refinements) and not regex.search(r"(?:AAC(?:v2)?|DTS|TRUE[ .-]*HD)$", self.title[: match.start()], regex.IGNORECASE):
                        continue
                emitted = value if value is not None else match.group(1)
                if field == "channels":
                    emitted = regex.sub(r"[ -]", ".", emitted)
                refinements.append((field, match.span(), emitted))
                if field == "audio":
                    start = regex.match(r"[ .-]*", self.title, pos=match.end()).end()
                    channels = regex.match(CHANNEL_LAYOUT_PATTERN, self.title, pos=start, flags=regex.IGNORECASE)
                    if channels and not NON_CHANNEL_UNIT_REGEX.match(self.title, channels.end()):
                        refinements.append(("channels", channels.span(), regex.sub(r"[ -]", ".", channels.group(1))))
        return refinements

    def process_technical_metadata(self, result: Dict[str, Any], refinements: List[Tuple[str, Tuple[int, int], str]]) -> None:
        """
        Replace overlapping coarse metadata while preserving separate occurrences.

        :param result: The parser result to update in place.
        :param refinements: Detailed values and their original match spans.
        """
        for field in ("audio", "channels", "hdr", "dolby_vision_profiles"):
            changes = [(span, value) for name, span, value in refinements if name == field]
            if not changes:
                continue
            recorded = [(span, value) for name, span, value in self.matches if name == field]
            retained = [value for span, value in recorded if not any(overlaps(span, location) for location, _ in changes)]
            retained += [value for value in result.get(field, []) if value not in {value for _, value in recorded}]
            result[field] = unique(retained + [value for _, value in changes])
        if result.get("dolby_vision_profiles"):
            result["hdr"] = unique(result.get("hdr", []) + ["DV"])
        if result.get("quality") == "HDTV":
            sources = [span for field, span, value in self.matches if field == "quality" and value == "HDTV"]
            codecs = [span for field, span, value in refinements if field == "audio" and value.startswith("DTS-HD")]
            if sources and all(any(codec[0] <= span[0] and span[1] <= codec[1] for codec in codecs) for span in sources):
                result.pop("quality")

    def apply(self, result: Dict[str, Any], translate: bool = False) -> None:
        """
        Apply language roles, regional tags and technical refinements to the parser result.

        :param result: The parser result to update in place.
        :param translate: Whether to translate audio and subtitle tags to display names.
        """
        overrides = {field: result[field] for field in self.overrides if field in result}
        removed = self.overrides.difference(result)
        refinements = self.find_technical_matches()
        self.process_languages(result, refinements)
        self.process_technical_metadata(result, refinements)
        for edition, field in (("Extended Edition", "extended"), ("Remastered", "remastered")):
            if result.get("edition") == edition:
                result[field] = True
        result.update(overrides)
        for field in removed:
            result.pop(field, None)
        for field in ("audio_languages", "subtitle_languages"):
            if field in overrides:
                result[field] = unique(transform_language(code) for code in overrides[field])
        if translate:
            from .parse import translate_langs

            for field in ("audio_languages", "subtitle_languages"):
                if field in result:
                    result[field] = translate_langs(result[field])
