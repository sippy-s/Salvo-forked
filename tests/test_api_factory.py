import json
from pathlib import Path

import pytest

from kernel.core.api_factory import ApiFactory
from kernel.exceptions import LoadApiTemplatesError, EmptyApiTemplatesError


@pytest.fixture
def mixed_api_file(tmp_path: Path) -> Path:
    path = tmp_path / "apis.json"

    path.write_text(
        json.dumps(
            [
                {
                    "source": "valid",
                    "url": "https://example.com/{phone}",
                    "method": "GET",
                    "capacity": 10,
                    "ticket": 5,
                },
                {"source": "missing-url", "method": "GET", "capacity": 10, "ticket": 5},
                {
                    "source": "invalid-url",
                    "url": "ffff",
                    "method": "GET",
                    "capacity": 10,
                    "ticket": 5,
                },
            ]
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def valid_api_file(tmp_path: Path) -> Path:
    path = tmp_path / "vali.json"

    path.write_text(
        json.dumps(
            [
                {
                    "source": "test.com",
                    "url": "https://example.com/98-{phone}",
                    "method": "POST",
                    "capacity": 10,
                    "ticket": 5,
                    "json": {"phone": "98-{phone}"},
                },
            ]
        ),
        encoding="utf-8",
    )
    return path


class TestApiFactory:

    def test_filters_invalid_templates(self, mixed_api_file: Path) -> None:
        factory = ApiFactory(mixed_api_file, {"phone": "9123456789"})
        factory.build()

        assert len(factory.api_slots) == 1
        assert factory.dropped_apis == 2

    def test_raises_when_all_templates_are_invalid(self, tmp_path: Path) -> None:
        path = tmp_path / "invalid.json"

        path.write_text(
            json.dumps(
                [
                    {"bad": "data"},
                ]
            ),
            encoding="utf-8",
        )

        factory = ApiFactory(path, {"phone": "9123456789"})

        with pytest.raises(EmptyApiTemplatesError):
            factory.build()

    def test_raises_when_file_does_not_exist(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"

        factory = ApiFactory(path, {"phone": "9123456789"})

        with pytest.raises(LoadApiTemplatesError):
            factory.build()

    def test_raises_on_malformed_json(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"

        path.write_text("{ invalid json", encoding="utf-8")

        factory = ApiFactory(path, {"phone": "9123456789"})

        with pytest.raises(LoadApiTemplatesError):
            factory.build()

    def test_injects_context_into_url(self, valid_api_file: Path) -> None:
        factory = ApiFactory(valid_api_file, {"phone": "9123456789"})
        factory.build()

        slot = factory.api_slots[0]

        assert slot.call.url == "https://example.com/98-9123456789"

    def test_injects_context_recursively(self, valid_api_file: Path) -> None:
        factory = ApiFactory(valid_api_file, {"phone": "9123456789"})
        factory.build()

        slot = factory.api_slots[0]

        assert slot.call.json == {"phone": "98-9123456789"}

    def test_builds_api_slot_correctly(self, valid_api_file: Path) -> None:
        factory = ApiFactory(valid_api_file, {"phone": "9123456789"})
        factory.build()

        slot = factory.api_slots[0]

        assert slot.call.source == "test.com"
        assert slot.call.method == "POST"

        assert slot.capacity == 10
        assert slot.ticket == 5
