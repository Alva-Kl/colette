"""Tests for colette_cli.utils.validation."""

from colette_cli.utils.validation import validate_project_name


VALID_NAMES = ["abc", "a1b", "my-project", "foo123", "a"]
INVALID_NAMES = ["", "-abc", "abc-", "ABC", "my_project", "a b"]


class TestValidateProjectName:
    def test_valid_names(self):
        for name in VALID_NAMES:
            assert validate_project_name(name), f"Expected '{name}' to be valid"

    def test_invalid_names(self):
        for name in INVALID_NAMES:
            assert not validate_project_name(name), f"Expected '{name}' to be invalid"
