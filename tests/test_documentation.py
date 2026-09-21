import doctest
from pathlib import Path
import shlex
import subprocess
import sys

import pytest
import regex

from PTT import Parser


def test_parser_docstring_example():
    test = doctest.DocTestParser().get_doctest(Parser.__doc__, {}, "Parser", None, 0)
    runner = doctest.DocTestRunner()
    runner.run(test)
    assert runner.failures == 0
    assert runner.tries > 0


@pytest.mark.parametrize("skip, remove, expected", [(False, False, "Movie"), (True, False, "Movie EXTRA tail"), (True, True, "Movie tail")])
def test_skip_from_title_does_not_remove_text(skip, remove, expected):
    parser = Parser()
    parser.add_handler("custom", regex.compile(r"\bEXTRA\b"), lambda value: True, {"skipFromTitle": skip, "remove": remove})
    assert parser.parse("Movie EXTRA tail")["title"] == expected


@pytest.mark.parametrize("command", ["combine", "dedupe"])
def test_makefile_keyword_commands(tmp_path, command):
    root = Path(__file__).resolve().parents[1]
    recipes = [shlex.split(line.strip().lstrip("@")) for line in (root / "Makefile").read_text().splitlines() if line.startswith("\t")]
    recipe = next(parts for parts in recipes if command in parts)
    assert recipe[:5] == ["uv", "run", "python", "-m", "PTT.cli"]
    input_file = tmp_path / "words.txt"
    input_file.write_text("beta\nalpha\nbeta\n", encoding="utf-8")
    target = tmp_path if command == "combine" else input_file
    result = subprocess.run([sys.executable, *recipe[3:-1], str(target)], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    output = tmp_path / "combined-keywords.txt" if command == "combine" else input_file
    assert output.read_text(encoding="utf-8").splitlines() == ["alpha", "beta"]
