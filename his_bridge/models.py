# =============================================================================
# FILE: his_bridge/models.py
# MÔ TẢ: Pydantic data models cho HIS Bridge.
#         Chuẩn hóa dữ liệu từ VNPT HIS trước khi push Firestore.
# =============================================================================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class HisIdentifiers(BaseModel):
    """Các mã định danh nội bộ từ VNPT HIS."""

    benh_nhan_id: str = Field(default="", description="BENHNHANID")
    tiep_nhan_id: str = Field(default="", description="TIEPNHANID")
    kham_benh_id: str = Field(default="", description="KHAMBENHID")
    mau_benh_pham_id: str = Field(default="", description="MAUBENHPHAMID")
    ho_so_benh_an_id: str = Field(default="", description="HOSOBENHANID")


class ServiceInfo(BaseModel):
    """Thông tin một dịch vụ chỉ định từ VNPT HIS."""

    code: str = Field(default="", description="MADICHVU — mã dịch vụ")
    name: str = Field(default="", description="TENDICHVU — tên dịch vụ đầy đủ")
    note: str = Field(default="", description="GHICHUCD — ghi chú chỉ định")
    status: str = Field(default="", description="TRANGTHAIDICHVU — trạng thái")


class PatientInfo(BaseModel):
    """Thông tin bệnh nhân đã chuẩn hóa từ VNPT HIS.

    Document này được push lên kiosk app để hiển thị
    và cho phép tiếp đón đẩy vào phòng siêu âm.
    """

    patient_code: str = Field(description="Mã bệnh nhân (barcode)")
    patient_name: str = Field(default="", description="TENBENHNHAN")
    age: int = Field(default=0, description="TUOI")
    gender: str = Field(default="", description="GIOITINH")
    address: str = Field(default="", description="DIACHI")
    status: str = Field(default="waiting", description="Trạng thái hàng đợi")
    his: HisIdentifiers = Field(
        default_factory=HisIdentifiers,
        description="Các mã HIS nội bộ",
    )
    services: list[ServiceInfo] = Field(
        default_factory=list,
        description="Danh sách dịch vụ chỉ định",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Thời điểm tạo (ISO 8601 UTC)",
    )

    def to_firestore_dict(self) -> dict[str, Any]:
        """Chuyển đổi sang dict format phù hợp cho Firestore document.

        Format output khớp với cấu trúc document yêu cầu:
        {
            "patientCode": "BN00280291",
            "patientName": "NGUYỄN TÂM NGÔN",
            "age": 41,
            ...
        }
        """
        return {
            "patientCode": self.patient_code,
            "patientName": self.patient_name,
            "age": self.age,
            "gender": self.gender,
            "address": self.address,
            "status": self.status,
            "his": {
                "benhNhanId": self.his.benh_nhan_id,
                "tiepNhanId": self.his.tiep_nhan_id,
                "khamBenhId": self.his.kham_benh_id,
                "mauBenhPhamId": self.his.mau_benh_pham_id,
                "hoSoBenhAnId": self.his.ho_so_benh_an_id,
            },
            "services": [
                {
                    "code": svc.code,
                    "name": svc.name,
                    "note": svc.note,
                }
                for svc in self.services
            ],
            "createdAt": self.created_at,
        }

    def service_names(self) -> list[str]:
        """Trả về danh sách tên dịch vụ để hiển thị trên kiosk."""
        return [svc.name for svc in self.services if svc.name]


class HisDocument(BaseModel):
    """Wrapper cho document hoàn chỉnh để push lên Firestore.

    Bao gồm PatientInfo + metadata bổ sung cho hàng đợi.
    """

    patient: PatientInfo
    room_number: str = Field(default="", description="Số phòng siêu âm")
    stt: str = Field(default="", description="Số thứ tự trong hàng đợi")
