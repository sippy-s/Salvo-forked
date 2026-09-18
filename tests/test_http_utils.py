from unittest.mock import AsyncMock, MagicMock

import pytest

from kernel.models.api import ApiCall
from kernel.utils.http_utils import send_single_request


class TestSendSingleRequest:

    @pytest.mark.asyncio
    async def test_get_request_returns_status(self) -> None:
        apicall = ApiCall(
            source="example.com",
            url="https://eample.com",
            method="GET",
            data=None,
            json=None,
        )

        response = MagicMock()
        response.status = 200

        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = response

        session = MagicMock()
        session.get.return_value = context_manager

        status = await send_single_request(
            session=session, apicall=apicall, timeout=10, headers={}
        )

        assert status == 200

        session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_request_returns_status(self) -> None:
        apicall = ApiCall(
            source="example.com",
            url="https://eample.com",
            method="POST",
            data=None,
            json={"phone": "9120000000"},
        )

        response = MagicMock()
        response.status = 201

        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = response

        session = MagicMock()
        session.post.return_value = context_manager

        status = await send_single_request(
            session=session, apicall=apicall, timeout=5, headers={}
        )

        assert status == 201

        session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsopported_method_returns_zero(self) -> None:
        apicall = ApiCall(
            source="example.com",
            url="https://eample.com",
            method="FTP",
            data=None,
            json=None,
        )

        session = MagicMock()

        status = await send_single_request(
            session=session, apicall=apicall, timeout=10, headers={}
        )

        assert status == 0

        session.get.assert_not_called()
        session.post.assert_not_called()
