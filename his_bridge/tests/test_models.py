# =============================================================================
# FILE: his_bridge/tests/test_models.py
# MÔ TẢ: Unit tests cho data models (PatientInfo, ServiceInfo, HisIdentifiers).
# =============================================================================

import pytest
from his_bridge.models import (
    HisDocument,
    HisIdentifiers,
    PatientInfo,
    ServiceInfo,
)


class TestServiceInfo:
    """Tests cho ServiceInfo model."""

    def test_create_default(self) -> None:
        """ServiceInfo mặc định có tất cả fields rỗng."""
        svc = ServiceInfo()
        assert svc.code == ""
        assert svc.name == ""
        assert svc.note == ""
        assert svc.status == ""

    def test_create_with_data(self) -> None:
        """ServiceInfo tạo với dữ liệu đầy đủ."""
        svc = ServiceInfo(
            code="CDHASA23",
            name="Siêu âm Doppler tim, van tim",
            note="DOPPLERTIM",
            status="waiting",
        )
        assert svc.code == "CDHASA23"
        assert svc.name == "Siêu âm Doppler tim, van tim"
        assert svc.note == "DOPPLERTIM"
        assert svc.status == "waiting"


class TestHisIdentifiers:
    """Tests cho HisIdentifiers model."""

    def test_create_default(self) -> None:
        """HisIdentifiers mặc định có tất cả fields rỗng."""
        ids = HisIdentifiers()
        assert ids.benh_nhan_id == ""
        assert ids.tiep_nhan_id == ""
        assert ids.kham_benh_id == ""
        assert ids.mau_benh_pham_id == ""
        assert ids.ho_so_benh_an_id == ""

    def test_create_with_data(self) -> None:
        """HisIdentifiers tạo với mã HIS thực tế."""
        ids = HisIdentifiers(
            benh_nhan_id="1034406",
            tiep_nhan_id="1670232",
            kham_benh_id="1622937",
            mau_benh_pham_id="15757827",
            ho_so_benh_an_id="999888",
        )
        assert ids.benh_nhan_id == "1034406"
        assert ids.mau_benh_pham_id == "15757827"


class TestPatientInfo:
    """Tests cho PatientInfo model."""

    @pytest.fixture()
    def sample_patient(self) -> PatientInfo:
        """Tạo PatientInfo mẫu cho test."""
        return PatientInfo(
            patient_code="BN00280291",
            patient_name="NGUYỄN TÂM NGÔN",
            age=41,
            gender="Nam",
            address="Sơn Trung 2",
            his=HisIdentifiers(
                benh_nhan_id="1034406",
                tiep_nhan_id="1670232",
                kham_benh_id="1622937",
                mau_benh_pham_id="15757827",
            ),
            services=[
                ServiceInfo(
                    code="CDHASA23",
                    name="Siêu âm Doppler tim, van tim",
                    note="DOPPLERTIM",
                ),
                ServiceInfo(
                    code="CDHASA01",
                    name="Siêu âm ổ bụng",
                    note="OBUNG",
                ),
            ],
        )

    def test_create_minimal(self) -> None:
        """PatientInfo tạo với thông tin tối thiểu (chỉ patient_code)."""
        patient = PatientInfo(patient_code="BN12345")
        assert patient.patient_code == "BN12345"
        assert patient.patient_name == ""
        assert patient.age == 0
        assert patient.status == "waiting"
        assert patient.services == []

    def test_service_names(self, sample_patient: PatientInfo) -> None:
        """service_names() trả về danh sách tên dịch vụ."""
        names = sample_patient.service_names()
        assert len(names) == 2
        assert "Siêu âm Doppler tim, van tim" in names
        assert "Siêu âm ổ bụng" in names

    def test_to_firestore_dict(self, sample_patient: PatientInfo) -> None:
        """to_firestore_dict() tạo dict đúng format cho Firestore."""
        result = sample_patient.to_firestore_dict()

        assert result["patientCode"] == "BN00280291"
        assert result["patientName"] == "NGUYỄN TÂM NGÔN"
        assert result["age"] == 41
        assert result["gender"] == "Nam"
        assert result["address"] == "Sơn Trung 2"
        assert result["status"] == "waiting"

        # HIS identifiers
        his = result["his"]
        assert his["benhNhanId"] == "1034406"
        assert his["tiepNhanId"] == "1670232"
        assert his["khamBenhId"] == "1622937"
        assert his["mauBenhPhamId"] == "15757827"

        # Services
        assert len(result["services"]) == 2
        assert result["services"][0]["code"] == "CDHASA23"
        assert result["services"][0]["name"] == "Siêu âm Doppler tim, van tim"
        assert result["services"][0]["note"] == "DOPPLERTIM"

        # Timestamp
        assert "createdAt" in result

    def test_to_firestore_dict_empty_services(self) -> None:
        """to_firestore_dict() với danh sách dịch vụ rỗng."""
        patient = PatientInfo(patient_code="BN99999")
        result = patient.to_firestore_dict()
        assert result["services"] == []

    def test_created_at_auto_generated(self) -> None:
        """created_at được tự động tạo khi không chỉ định."""
        patient = PatientInfo(patient_code="BN00001")
        assert patient.created_at  # Không rỗng
        assert "T" in patient.created_at  # ISO format


class TestHisDocument:
    """Tests cho HisDocument wrapper."""

    def test_create(self) -> None:
        """HisDocument wrap PatientInfo + room info."""
        patient = PatientInfo(
            patient_code="BN12345",
            patient_name="TEST",
        )
        doc = HisDocument(
            patient=patient,
            room_number="3",
            stt="005",
        )
        assert doc.patient.patient_code == "BN12345"
        assert doc.room_number == "3"
        assert doc.stt == "005"
