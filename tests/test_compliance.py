import pytest

from mediaforge.workers.compliance.checker import ComplianceChecker


@pytest.fixture
def checker():
    return ComplianceChecker()


def test_l1_blocks_dangerous_intent(checker):
    result = checker.check(
        sku={"market": "US", "output_types": ["main_image"]},
        prompt="how to make a bomb",
    )
    assert result.blocked is True


def test_l4_fixes_china_number(checker):
    result = checker.check(
        sku={"market": "CN", "output_types": ["main_image"]},
        prompt="price 4 dollars",
    )
    assert "6" in result.modified_prompt
    assert "4" not in result.modified_prompt
    assert result.auto_fixed is True


def test_l5_adds_platform_spec(checker):
    result = checker.check(
        sku={"market": "US", "output_types": ["main_image"], "target_platforms": ["amazon"]},
        prompt="white background product photo",
    )
    assert "amazon" in result.modified_prompt.lower()
