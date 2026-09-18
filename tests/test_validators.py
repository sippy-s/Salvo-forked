import pytest

from kernel.utils.validators import ApiValidator, phone_validator, proxy_validator
from kernel.exceptions import (
    MalformedPhoneNumberError,
    MalformedProxyError,
    UnsupportedProxyError,
)


class TestApiValidation:

    def test_valid_api_config(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
        }

        assert ApiValidator.validate(config) is True

    @pytest.mark.parametrize("source", ["", "   ", "#bad", "   #hidden"])
    def test_invalid_source(self, source) -> None:
        config = {
            "source": source,
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
        }
        assert ApiValidator.validate(config) is False

    @pytest.mark.parametrize("value", [0, -1, -10])
    def test_invalid_capacity_ticket(self, value):
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 20,
            "ticket": value,
        }
        assert ApiValidator.validate(config) is False

    def test_missing_required_field(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
        }
        assert ApiValidator.validate(config) is False

    def test_bool_not_allowed_as_int(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": True,
            "ticket": 5,
        }
        assert ApiValidator.validate(config) is False

    def test_invalid_method(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "DELETE",
            "capacity": 10,
            "ticket": 5,
        }
        assert ApiValidator.validate(config) is False

    def test_both_json_and_data_payload(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
            "json": {},
            "data": {},
        }
        assert ApiValidator.validate(config) is False

    def test_valid_payload_none(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
            "json": None,
            "data": None,
        }
        assert ApiValidator.validate(config) is True

    def test_valid_single_json_payload(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
            "json": {},
            "data": None,
        }
        assert ApiValidator.validate(config) is True

    def test_valid_single_json_payload(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
            "json": None,
            "data": {},
        }
        assert ApiValidator.validate(config) is True


class TestPhoneValidation:

    def test_valid_phone_with_0_prefix(self) -> None:
        phone = "09123456789"
        assert phone_validator(phone) == "9123456789"

    def test_valid_phone_with_98_prefix(self) -> None:
        phone = "+989123456789"
        assert phone_validator(phone) == "9123456789"

    def test_valid_phone_with_noise(self) -> None:
        phone = "  +98 (912-345-6789) "
        assert phone_validator(phone) == "9123456789"

    def test_invalid_type(self) -> None:
        with pytest.raises(MalformedPhoneNumberError):
            phone_validator(912345678)

    def test_invalid_format(self) -> None:
        with pytest.raises(MalformedPhoneNumberError):
            phone_validator("12345667")


class TestProxyValidation:

    def test_valid_http_proxy(self) -> None:
        proxy = "http://example.com:9090"
        assert proxy_validator(proxy) == proxy

    def test_valid_https_proxy(self) -> None:
        proxy = "https://example.com:9090"
        assert proxy_validator(proxy) == proxy

    def test_invalid_format(self) -> None:
        with pytest.raises(MalformedProxyError):
            proxy_validator("1.2.3.4:9090")

    def test_unsupported_scheme(self) -> None:
        with pytest.raises(UnsupportedProxyError):
            proxy_validator("socks5://127.0.0.1:9050")

    def test_invalid_type(self) -> None:
        with pytest.raises(MalformedProxyError):
            proxy_validator(123456)
