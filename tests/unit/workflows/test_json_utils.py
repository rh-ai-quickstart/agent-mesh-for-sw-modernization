import pytest
from utils.json_utils import extract_json_from_string


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('prefix {"status": "complete"} suffix', {"status": "complete"}),
        ('```json\n{"files": 2}\n```', {"files": 2}),
        ("Result: [1, 2, 3]", [1, 2, 3]),
    ],
)
def test_extract_json_from_model_output(text, expected):
    assert extract_json_from_string(text) == expected


def test_extract_json_returns_none_for_invalid_text():
    assert extract_json_from_string("no structured response") is None
