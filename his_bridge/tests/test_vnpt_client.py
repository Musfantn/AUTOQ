# =============================================================================
# FILE: his_bridge/tests/test_vnpt_client.py
# MÔ TẢ: Unit tests cho VNPTHisClient với mock httpx responses.
# =============================================================================

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from his_bridge.config import HisConfig
from his_bridge.models import PatientInfo
from his_bridge.vnpt_his_client import (
    HisConnectionError,
    SessionExpiredError,
    VNPTHisClient,
)


@pytest.fixture()
def sample_config() -> HisConfig:
    """Config mẫu cho test — không kết nối thật."""
    return HisConfig.load(None)  # Load defaults


@pytest.fixture()
def mock_search_response() -> dict[str, Any]:
    """Response mẫu từ ajaxExecuteQueryPaging (CLS02C001.SIDS)."""
    return {
        "data": [
            {
                "MAUBENHPHAMID": "15757827",
                "BENHNHANID": "1034406",
                "TIEPNHANID": "1670232",
                "TENBENHNHAN": "NGUYỄN TÂM NGÔN",
                "NGAYSINH": "1985-03-15",
                "GIOITINH": "Nam",
                "TUOI": 41,
            }
        ]
    }


@pytest.fixture()
def mock_info_response() -> dict[str, Any]:
    """Response mẫu từ ajaxCALL_SP_O (NGT02K016.EV003)."""
    return {
        "TENBENHNHAN": "NGUYỄN TÂM NGÔN",
        "TUOI": 41,
        "DIACHI": "Sơn Trung 2",
        "KHAMBENHID": "1622937",
        "TIEPNHANID": "1670232",
        "HOSOBENHANID": "999888",
    }


@pytest.fixture()
def mock_services_response() -> list[dict[str, Any]]:
    """Response mẫu từ ajaxCALL_SP_O (CLS02C001.DSKQ)."""
    return [
        {
            "MADICHVU": "CDHASA23",
            "TENDICHVU": "Siêu âm Doppler tim, van tim",
            "GHICHUCD": "DOPPLERTIM",
            "TRANGTHAIDICHVU": "waiting",
        },
        {
            "MADICHVU": "CDHASA01",
            "TENDICHVU": "Siêu âm ổ bụng",
            "GHICHUCD": "OBUNG",
            "TRANGTHAIDICHVU": "waiting",
        },
    ]


class TestVNPTHisClient:
    """Tests cho VNPTHisClient."""

    def test_parse_response_json(self) -> None:
        """_parse_response() parse JSON string đúng."""
        result = VNPTHisClient._parse_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_response_empty(self) -> None:
        """_parse_response() trả về dict rỗng cho response rỗng."""
        result = VNPTHisClient._parse_response("")
        assert result == {}

    def test_parse_response_wrapped_json(self) -> None:
        """_parse_response() xử lý JSON wrapped trong text khác."""
        text = 'some prefix {"data": [1, 2, 3]} some suffix'
        result = VNPTHisClient._parse_response(text)
        assert result == {"data": [1, 2, 3]}

    def test_parse_response_invalid(self) -> None:
        """_parse_response() trả về raw text khi không parse được."""
        result = VNPTHisClient._parse_response("plain text without json")
        assert result == {"raw": "plain text without json"}

    def test_extract_patient_from_search_with_data_key(
        self,
        mock_search_response: dict[str, Any],
    ) -> None:
        """_extract_patient_from_search() lấy row đầu tiên từ 'data' key."""
        result = VNPTHisClient._extract_patient_from_search(
            mock_search_response,
        )
        assert result["MAUBENHPHAMID"] == "15757827"
        assert result["TENBENHNHAN"] == "NGUYỄN TÂM NGÔN"

    def test_extract_patient_from_search_flat_dict(self) -> None:
        """_extract_patient_from_search() xử lý flat dict có MAUBENHPHAMID."""
        flat = {"MAUBENHPHAMID": "12345", "TENBENHNHAN": "TEST"}
        result = VNPTHisClient._extract_patient_from_search(flat)
        assert result["MAUBENHPHAMID"] == "12345"

    def test_normalize_patient(
        self,
        mock_info_response: dict[str, Any],
        mock_services_response: list[dict[str, Any]],
    ) -> None:
        """_normalize_patient() tạo PatientInfo đầy đủ từ raw data."""
        search_data = {
            "MAUBENHPHAMID": "15757827",
            "BENHNHANID": "1034406",
        }

        patient = VNPTHisClient._normalize_patient(
            barcode="BN00280291",
            search_data=search_data,
            info_data=mock_info_response,
            services_data=mock_services_response,
        )

        assert isinstance(patient, PatientInfo)
        assert patient.patient_code == "BN00280291"
        assert patient.patient_name == "NGUYỄN TÂM NGÔN"
        assert patient.age == 41
        assert patient.address == "Sơn Trung 2"
        assert patient.his.benh_nhan_id == "1034406"
        assert patient.his.mau_benh_pham_id == "15757827"
        assert len(patient.services) == 2
        assert patient.services[0].code == "CDHASA23"
        assert patient.services[1].name == "Siêu âm ổ bụng"

    def test_normalize_patient_missing_info(self) -> None:
        """_normalize_patient() xử lý khi info_data rỗng."""
        search_data = {
            "MAUBENHPHAMID": "12345",
            "TENBENHNHAN": "FALLBACK NAME",
            "TUOI": 30,
            "GIOITINH": "Nữ",
        }

        patient = VNPTHisClient._normalize_patient(
            barcode="BN99999",
            search_data=search_data,
            info_data={},
            services_data=[],
        )

        assert patient.patient_name == "FALLBACK NAME"
        assert patient.age == 30
        assert patient.gender == "Nữ"
        assert patient.services == []

    def test_build_minimal_patient(self) -> None:
        """_build_minimal_patient() tạo patient tối thiểu."""
        patient = VNPTHisClient._build_minimal_patient(
            barcode="BN11111",
            search_data={"TENBENHNHAN": "MINIMAL"},
        )
        assert patient.patient_code == "BN11111"
        assert patient.patient_name == "MINIMAL"
        assert patient.services == []

    def test_build_service_params(self, sample_config: HisConfig) -> None:
        """build_service_params() tạo chuỗi tham số đúng format."""
        client = VNPTHisClient(sample_config)
        params = client.build_service_params("15757827")

        # Format: {room_id}${database_name}${hospital_id}${department_id}${mau_benh_pham_id}
        parts = params.split("$")
        assert len(parts) == 5
        assert parts[-1] == "15757827"


class TestVNPTHisClientAsync:
    """Async tests cho VNPTHisClient (mock httpx)."""

    @pytest.mark.asyncio()
    async def test_search_patient_success(
        self,
        sample_config: HisConfig,
        mock_search_response: dict[str, Any],
    ) -> None:
        """search_patient() gọi API và parse response đúng."""
        client = VNPTHisClient(sample_config)

        mock_response = httpx.Response(
            status_code=200,
            text=json.dumps(mock_search_response),
            request=httpx.Request("POST", "http://test"),
        )

        with patch.object(
            httpx.AsyncClient, "post", return_value=mock_response,
        ):
            async with client:
                result = await client.search_patient("BN00280291")

        assert "data" in result

    @pytest.mark.asyncio()
    async def test_session_expired_401(
        self,
        sample_config: HisConfig,
    ) -> None:
        """search_patient() raise SessionExpiredError khi HTTP 401."""
        client = VNPTHisClient(sample_config)

        mock_response = httpx.Response(
            status_code=401,
            text="Unauthorized",
            request=httpx.Request("POST", "http://test"),
        )

        with patch.object(
            httpx.AsyncClient, "post", return_value=mock_response,
        ):
            async with client:
                with pytest.raises(SessionExpiredError):
                    await client.search_patient("BN00280291")

    @pytest.mark.asyncio()
    async def test_connection_error_retry(
        self,
        sample_config: HisConfig,
    ) -> None:
        """search_patient() retry khi timeout và raise HisConnectionError."""
        client = VNPTHisClient(sample_config)

        with patch.object(
            httpx.AsyncClient,
            "post",
            side_effect=httpx.TimeoutException("timeout"),
        ):
            async with client:
                with pytest.raises(HisConnectionError):
                    await client.search_patient("BN00280291")
