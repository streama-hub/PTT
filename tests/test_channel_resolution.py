import pytest
import regex

from PTT import parse_title
from PTT.metadata import CHANNEL_LAYOUT_PATTERN


@pytest.mark.parametrize("codec", ["DTS-HD.MA.", "TrueHD.Atmos.", "AAC", "HE-AACv2."])
@pytest.mark.parametrize("resolution", ["480p", "720p", "1080p", "1080i", "2160p", "4320p"])
def test_complex_channels_before_resolution(codec, resolution):
    result = parse_title(f"Example.2024.{codec}7.1.4.{resolution}.x265-GRP")
    assert result["channels"] == ["7.1.4"]


@pytest.mark.parametrize("suffix", [".2", ".1080", ".2160pixels", ".1080p2", ".2160pExtra", ".1.1080p"])
def test_complex_channels_do_not_accept_extra_numeric_components(suffix):
    assert regex.fullmatch(CHANNEL_LAYOUT_PATTERN, "7.1.4" + suffix) is None
    assert regex.match(CHANNEL_LAYOUT_PATTERN, "7.1.4" + suffix) is None
