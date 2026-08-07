# =============================================================================
# FILE: his_bridge/vnpt_his_client.py
# MÔ TẢ: Async HTTP client giao tiếp trực tiếp với VNPT HIS RestService.
#         Sử dụng httpx.AsyncClient với connection pooling, cookie management,
#         retry logic, và browser-like headers.
#
#         KHÔNG SỬ DỤNG: Selenium, Playwright, OCR, HTML parsing.
#         TẤT CẢ DỮ LIỆU lấy qua RestService (POST request).
# =============================================================================

from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
from datetime import datetime
from typing import Any

import httpx

from his_bridge.config import HisConfig
from his_bridge.logger import get_logger, log_timing
from his_bridge.models import HisIdentifiers, PatientInfo, ServiceInfo


class SessionExpiredError(Exception):
    """Lỗi khi session VNPT HIS đã hết hạn."""


class HisConnectionError(Exception):
    """Lỗi kết nối tới VNPT HIS RestService."""


class PatientNotFoundError(Exception):
    """Lỗi khi không tìm thấy bệnh nhân trên VNPT HIS."""


class ParserError(Exception):
    """Lỗi khi parse dữ liệu từ VNPT HIS thất bại."""


class VNPTHisClient:
    """Async HTTP client cho VNPT HIS RestService.

    Gửi POST requests tới RestService endpoint, tái sử dụng session
    (JSESSIONID + JWT uuid), quản lý connection pool.

    Attributes:
        config: Cấu hình HIS từ HisConfig.
        client: httpx.AsyncClient instance (lazy init).

    Ví dụ::

        async with VNPTHisClient(config) as his:
            patient = await his.fetch_full_patient("BN00280291")
            print(patient.patient_name)
    """

    def __init__(self, config: HisConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._logger = get_logger("his_bridge.vnpt_client")

    async def __aenter__(self) -> VNPTHisClient:
        """Khởi tạo httpx.AsyncClient với connection pool và cookies."""
        self._client = self._create_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Đóng connection pool khi thoát context."""
        await self.close()

    def _create_client(self) -> httpx.AsyncClient:
        """Tạo httpx.AsyncClient với cấu hình đầy đủ."""
        his = self._config.his
        net = self._config.network

        # Xây dựng cookies từ session config
        cookies = httpx.Cookies()
        headers = dict(his.headers)
        cookie_list = []
        if his.session.jsessionid:
            cookies.set(
                "JSESSIONID", his.session.jsessionid,
                domain="bvhatinh.vncare.vn", path="/vnpthis/",
            )
            cookie_list.append(f"JSESSIONID={his.session.jsessionid}")
        if his.session.sessionid:
            cookies.set(
                "SESSIONID", his.session.sessionid,
                domain="bvhatinh.vncare.vn", path="/",
            )
            cookie_list.append(f"SESSIONID={his.session.sessionid}")
            
        if cookie_list:
            headers["Cookie"] = "; ".join(cookie_list)

        # Connection pool limits
        limits = httpx.Limits(
            max_connections=net.connection_pool_size,
            max_keepalive_connections=net.connection_pool_size,
        )

        return httpx.AsyncClient(
            headers=headers,
            cookies=cookies,
            timeout=httpx.Timeout(
                timeout=float(net.timeout_seconds),
                connect=5.0,
            ),
            limits=limits,
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Đóng HTTP client và giải phóng connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Đảm bảo client đã được khởi tạo."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    async def _post_with_retry(
        self,
        body: dict[str, Any],
        as_json: bool = True,
        url_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Gửi POST request tới RestService với retry logic.

        Args:
            body: Dictionary payload.
            as_json: Nếu True, gửi dưới dạng JSON body. 
                     Nếu False, gửi dưới dạng application/x-www-form-urlencoded.
            url_params: Dictionary các query parameters để đính kèm vào URL.

        Returns:
            Parsed JSON response dict.

        Raises:
            SessionExpiredError: Nếu session hết hạn.
            HisConnectionError: Nếu kết nối thất bại sau tất cả retry.
        """
        client = self._ensure_client()
        net = self._config.network
        his = self._config.his

        # Thêm uuid JWT vào body nếu gửi dạng JSON và chưa có
        if as_json and his.session.uuid_jwt and "uuid" not in body:
            body["uuid"] = his.session.uuid_jwt

        last_error: Exception | None = None

        for attempt in range(1, net.max_retries + 1):
            try:
                # Log detailed request for debugging
                self._logger.info(
                    "CDP Request: URL=%s | Params=%s | Body=%s",
                    his.base_url,
                    url_params,
                    json.dumps(body, ensure_ascii=False)[:1000]
                )

                if as_json:
                    response = await client.post(
                        his.base_url,
                        json=body,
                        params=url_params,
                        headers={"Content-Type": "application/json; charset=UTF-8"}
                    )
                else:
                    response = await client.post(
                        his.base_url,
                        data=body,
                        params=url_params,
                        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
                    )

                response_text = response.text

                # Log detailed response for debugging
                self._logger.info(
                    "CDP Response: Status=%d | Headers=%s | Body=%s",
                    response.status_code,
                    dict(response.headers),
                    response_text[:2000]
                )

                # 1. Kiểm tra session expired qua HTTP status code
                if response.status_code in (401, 403):
                    raise SessionExpiredError(
                        f"Session HIS đã hết hạn (HTTP {response.status_code}). "
                        "Vui lòng cập nhật JSESSIONID và uuid trong config.yaml."
                    )

                # 2. Kiểm tra redirect về trang login
                if "login" in response.url.path.lower():
                    raise SessionExpiredError(
                        "Session HIS đã hết hạn — bị redirect về trang đăng nhập. "
                        "Vui lòng cập nhật JSESSIONID trong config.yaml."
                    )

                response.raise_for_status()
                parsed_res = self._parse_response(response_text)

                # 3. Kiểm tra session expired qua response body (e.g. {"result":"session=NULL"})
                if isinstance(parsed_res, dict):
                    res_val = parsed_res.get("result")
                    err_code = parsed_res.get("error_code")
                    err_msg = parsed_res.get("error_msg", "")
                    
                    if (res_val == "session=NULL" or 
                        err_code == 2 or 
                        "session is null" in str(err_msg).lower() or 
                        "session is null" in str(res_val).lower() or
                        "session is null" in response_text.lower()):
                        raise SessionExpiredError(
                            "Session HIS đã hết hạn (lỗi session=NULL từ response body). "
                            "Vui lòng cập nhật JSESSIONID và uuid trong config.yaml."
                        )

                return parsed_res

            except SessionExpiredError:
                raise  # Không retry khi session hết hạn

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                self._logger.warning(
                    "Lần thử %d/%d thất bại: %s",
                    attempt,
                    net.max_retries,
                    exc,
                )
                if attempt < net.max_retries:
                    delay = net.retry_delay_seconds * attempt
                    await asyncio.sleep(delay)

            except httpx.HTTPStatusError as exc:
                last_error = exc
                self._logger.error(
                    "HTTP %d từ HIS: %s",
                    exc.response.status_code,
                    exc.response.text[:200],
                )
                if attempt < net.max_retries:
                    delay = net.retry_delay_seconds * attempt
                    await asyncio.sleep(delay)

        raise HisConnectionError(
            f"Không thể kết nối VNPT HIS sau {net.max_retries} lần thử. "
            f"Lỗi cuối: {last_error}"
        )

    @staticmethod
    def _parse_response(text: str) -> dict[str, Any]:
        """Parse response text từ HIS RestService.

        VNPT HIS có thể trả về JSON hoặc JSON wrapped trong một số format.
        Method này xử lý cả hai trường hợp.
        """
        text = text.strip()

        # Xử lý trường hợp response rỗng
        if not text:
            return {}

        try:
            res = json.loads(text)
            # Tự động unpack stringified JSON trong 'result' key nếu có
            if isinstance(res, dict) and "result" in res and isinstance(res["result"], str):
                val = res["result"].strip()
                if (val.startswith("[") and val.endswith("]")) or (val.startswith("{") and val.endswith("}")):
                    try:
                        res["result"] = json.loads(val)
                    except json.JSONDecodeError:
                        pass
            return res
        except json.JSONDecodeError:
            pass

        # Một số endpoint HIS trả về format khác (e.g., text/plain với JSON bên trong)
        # Thử tìm JSON object hoặc array trong text
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start_idx = text.find(start_char)
            end_idx = text.rfind(end_char)
            if start_idx != -1 and end_idx > start_idx:
                try:
                    res = json.loads(text[start_idx:end_idx + 1])
                    if isinstance(res, dict) and "result" in res and isinstance(res["result"], str):
                        val = res["result"].strip()
                        if (val.startswith("[") and val.endswith("]")) or (val.startswith("{") and val.endswith("}")):
                            try:
                                res["result"] = json.loads(val)
                            except json.JSONDecodeError:
                                pass
                    return res
                except json.JSONDecodeError:
                    continue

        return {"raw": text}

    # ─── PUBLIC API METHODS ─────────────────────────────────────────────

    @log_timing
    async def search_patient(self, barcode: str) -> dict[str, Any]:
        """Bước 2: Tìm kiếm bệnh nhân bằng mã barcode.

        Gọi ajaxExecuteQueryPaging với stored procedure CLS02C001.SIDS.

        Args:
            barcode: Mã bệnh nhân từ barcode scanner (ví dụ: "BN00280291").

        Returns:
            Dict chứa MAUBENHPHAMID, BENHNHANID, TIEPNHANID, TENBENHNHAN, ...

        Raises:
            SessionExpiredError: Session hết hạn.
            HisConnectionError: Lỗi kết nối.
        """
        his = self._config.his
        sp = his.stored_procedures
        today_str = datetime.now().strftime("%d/%m/%Y")

        body = {
            "func": "ajaxExecuteQueryPaging",
            "params": [sp.search],
            "options": [
                {"name": "[0]", "value": his.room_id},
                {"name": "[1]", "value": his.database_name},
                {"name": "[2]", "value": his.hospital_id},
                {"name": "[3]", "value": his.department_id},
                {"name": "[4]", "value": his.extra_id},
                {"name": "[5]", "value": today_str},
                {"name": "[6]", "value": today_str},
                {"name": "[7]", "value": "2"},
                {"name": "[8]", "value": barcode}
            ]
        }

        url_params = {
            "_search": "false",
            "nd": str(int(time.time() * 1000)),
            "rows": "5",
            "page": "1",
            "sidx": "",
            "sord": "asc"
        }

        self._logger.info(
            "Tìm kiếm bệnh nhân barcode='%s' (SP: %s)",
            barcode,
            sp.search,
        )

        result = await self._post_with_retry(
            body,
            as_json=True,
            url_params=url_params,
        )
        return result

    @log_timing
    async def get_patient_info(
        self,
        mau_benh_pham_id: str,
    ) -> dict[str, Any]:
        """Bước 3: Lấy thông tin chi tiết bệnh nhân.

        Gọi ajaxCALL_SP_O với stored procedure NGT02K016.EV003.

        Args:
            mau_benh_pham_id: MAUBENHPHAMID từ bước tìm kiếm.

        Returns:
            Dict chứa TENBENHNHAN, TUOI, DIACHI, KHAMBENHID, ...
        """
        his = self._config.his
        sp = his.stored_procedures

        body = {
            "func": "ajaxCALL_SP_O",
            "params": [
                sp.patient_info,
                mau_benh_pham_id,
                0
            ]
        }

        self._logger.info(
            "Lấy thông tin BN (mauBenhPhamId=%s, SP: %s)",
            mau_benh_pham_id,
            sp.patient_info,
        )

        result = await self._post_with_retry(body)
        return result

    @log_timing
    async def get_services(self, params: str) -> list[dict[str, Any]]:
        """Bước 4: Lấy danh sách dịch vụ chỉ định.

        Gọi ajaxCALL_SP_O với stored procedure CLS02C001.DSKQ.

        Args:
            params: Chuỗi tham số phân tách bằng '$'.
                    Ví dụ: "77846$HIS_DATA_HTH_KYANH$42$26060$15757827"
                    Các giá trị lấy từ config:
                    - room_id (77846)
                    - database_name (HIS_DATA_HTH_KYANH)
                    - hospital_id (42)
                    - department_id (26060)
                    - mau_benh_pham_id (15757827)

        Returns:
            List các dict dịch vụ chứa MADICHVU, TENDICHVU, GHICHUCD, ...
        """
        his = self._config.his
        sp = his.stored_procedures

        body = {
            "func": "ajaxCALL_SP_O",
            "params": [
                sp.services,
                params,
                0
            ]
        }

        self._logger.info(
            "Lấy dịch vụ chỉ định (params=%s, SP: %s)",
            params,
            sp.services,
        )

        result = await self._post_with_retry(body)

        # Response có thể là list trực tiếp hoặc wrapped trong key
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            # Thử tìm list dịch vụ trong các key phổ biến
            for key in ("data", "rows", "items", "result", "records"):
                if key in result and isinstance(result[key], list):
                    return result[key]
            # Nếu không tìm thấy list, wrap dict thành list 1 phần tử
            return [result] if result else []
        return []

    def build_service_params(self, mau_benh_pham_id: str) -> str:
        """Xây dựng chuỗi tham số cho API get_services từ config.

        Format: "{room_id}${database_name}${hospital_id}${department_id}${mau_benh_pham_id}"

        Args:
            mau_benh_pham_id: MAUBENHPHAMID từ bước tìm kiếm.

        Returns:
            Chuỗi tham số phân tách bằng '$'.
        """
        his = self._config.his
        return (
            f"{his.room_id}${his.database_name}"
            f"${his.hospital_id}${his.department_id}"
            f"${mau_benh_pham_id}"
        )

    @log_timing
    async def fetch_full_patient(self, barcode: str) -> PatientInfo:
        """Orchestrator: Thực hiện toàn bộ luồng tra cứu bệnh nhân.

        1. search_patient(barcode) → lấy MAUBENHPHAMID
        2. asyncio.gather(get_patient_info, get_services) → gọi song song
        3. Chuẩn hóa kết quả thành PatientInfo

        Args:
            barcode: Mã bệnh nhân từ barcode scanner.

        Returns:
            PatientInfo đã chuẩn hóa đầy đủ.
        """
        start_time = time.perf_counter()
        normalized_barcode = barcode.strip()
        self._logger.info("Tra cứu bệnh nhân: barcode gốc='%s' -> barcode chuẩn hóa='%s'", barcode, normalized_barcode)

        # Bước 1: Tìm kiếm
        search_result = await self.search_patient(normalized_barcode)

        if isinstance(search_result, dict) and "error_msg" in search_result and search_result.get("error_code") != 0:
            err_msg = search_result.get("error_msg", "Unknown error")
            raise ParserError(f"HIS API trả về lỗi: {err_msg} (code={search_result.get('error_code')})")

        patient_data = self._extract_patient_from_search(search_result)

        if not patient_data or not isinstance(patient_data, dict):
            raise PatientNotFoundError(f"Không tìm thấy bệnh nhân với mã '{normalized_barcode}' trên hệ thống HIS.")

        # Lấy MAUBENHPHAMID case-insensitive
        mau_benh_pham_id = str(self._get_case_insensitive(patient_data, "MAUBENHPHAMID", ""))
        benh_nhan_id = str(self._get_case_insensitive(patient_data, "BENHNHANID", ""))

        if not mau_benh_pham_id:
            has_rows = False
            if isinstance(search_result, dict):
                rows = self._find_first_list_of_dicts(search_result)
                if rows:
                    has_rows = True
            
            if has_rows:
                raise ParserError(f"Lỗi cấu trúc dữ liệu HIS: Kết quả tìm kiếm của mã '{normalized_barcode}' thiếu trường MAUBENHPHAMID.")
            else:
                raise PatientNotFoundError(f"Không tìm thấy bệnh nhân với mã '{normalized_barcode}' trên hệ thống HIS.")

        self._logger.info(
            "Đã tìm thấy MAUBENHPHAMID='%s' và BENHNHANID='%s' cho mã '%s'",
            mau_benh_pham_id,
            benh_nhan_id,
            normalized_barcode,
        )

        # Bước 2 & 3: Gọi song song
        service_params = self.build_service_params(mau_benh_pham_id)

        info_result, services_result = await asyncio.gather(
            self.get_patient_info(mau_benh_pham_id),
            self.get_services(service_params),
            return_exceptions=True,
        )

        if isinstance(info_result, Exception):
            self._logger.error("Lỗi lấy thông tin BN chi tiết: %s", info_result, exc_info=True)
            raise ParserError(f"Không thể lấy thông tin chi tiết bệnh nhân (MAUBENHPHAMID={mau_benh_pham_id}): {info_result}")

        if isinstance(services_result, Exception):
            self._logger.error("Lỗi lấy danh sách dịch vụ: %s", services_result, exc_info=True)
            raise ParserError(f"Không thể lấy danh sách dịch vụ chỉ định (MAUBENHPHAMID={mau_benh_pham_id}): {services_result}")

        # Trích xuất flat dict từ info_result
        info_data = self._extract_patient_from_search(info_result) if isinstance(info_result, dict) else {}
        services_data = services_result if isinstance(services_result, list) else []

        patient_info = self._normalize_patient(
            barcode=normalized_barcode,
            search_data=patient_data,
            info_data=info_data,
            services_data=services_data,
        )

        elapsed = (time.perf_counter() - start_time) * 1000
        self._logger.info(
            "Tra cứu bệnh nhân hoàn thành: Mã='%s' | Tên='%s' | MAUBENHPHAMID='%s' | BENHNHANID='%s' | Số dịch vụ=%d | Thời gian=%.1f ms",
            normalized_barcode,
            patient_info.patient_name,
            patient_info.his.mau_benh_pham_id,
            patient_info.his.benh_nhan_id,
            len(patient_info.services),
            elapsed,
        )
        return patient_info

    # ─── PRIVATE HELPERS ────────────────────────────────────────────────

    @staticmethod
    def _get_case_insensitive(d: dict[str, Any], key: str, default: Any = "") -> Any:
        """Lấy giá trị từ dict không phân biệt chữ hoa chữ thường."""
        k_lower = key.lower().replace("_", "")
        for k, v in d.items():
            if k.lower().replace("_", "") == k_lower:
                return v
        return default

    @classmethod
    def _find_first_list_of_dicts(cls, obj: Any) -> list[dict[str, Any]] | None:
        """Đệ quy tìm list of dicts đầu tiên trong JSON structure."""
        if isinstance(obj, list):
            if obj and all(isinstance(x, dict) for x in obj):
                return obj
            for x in obj:
                res = cls._find_first_list_of_dicts(x)
                if res:
                    return res
        elif isinstance(obj, dict):
            for key in ("rows", "data", "items", "records", "result"):
                if key in obj:
                    val = obj[key]
                    if isinstance(val, list) and all(isinstance(x, dict) for x in val):
                        return val
                    elif isinstance(val, dict):
                        res = cls._find_first_list_of_dicts(val)
                        if res:
                            return res
            for key, val in obj.items():
                if key not in ("rows", "data", "items", "records", "result"):
                    res = cls._find_first_list_of_dicts(val)
                    if res:
                        return res
        return None

    @classmethod
    def _extract_patient_from_search(
        cls,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Trích xuất thông tin bệnh nhân từ kết quả search.

        VNPT HIS trả về dạng paging data — cần tìm row đầu tiên.
        """
        rows = cls._find_first_list_of_dicts(result)
        if rows:
            return rows[0]

        if cls._get_case_insensitive(result, "MAUBENHPHAMID"):
            return result

        return result

    @classmethod
    def _normalize_patient(
        cls,
        barcode: str,
        search_data: dict[str, Any],
        info_data: dict[str, Any],
        services_data: list[dict[str, Any]],
    ) -> PatientInfo:
        """Chuẩn hóa dữ liệu thô từ HIS thành PatientInfo model."""
        patient_name = (
            cls._get_case_insensitive(info_data, "TENBENHNHAN")
            or cls._get_case_insensitive(search_data, "TENBENHNHAN")
            or ""
        )

        age_raw = (
            cls._get_case_insensitive(info_data, "TUOI")
            or cls._get_case_insensitive(search_data, "TUOI")
            or 0
        )
        try:
            if isinstance(age_raw, str) and "." in age_raw:
                age = int(float(age_raw))
            else:
                age = int(age_raw)
        except (ValueError, TypeError):
            age = 0

        gender = (
            cls._get_case_insensitive(info_data, "GIOITINH")
            or cls._get_case_insensitive(search_data, "GIOITINH")
            or ""
        )

        address = (
            cls._get_case_insensitive(info_data, "DIACHI")
            or cls._get_case_insensitive(search_data, "DIACHI")
            or ""
        )

        his_ids = HisIdentifiers(
            benh_nhan_id=str(
                cls._get_case_insensitive(info_data, "BENHNHANID")
                or cls._get_case_insensitive(search_data, "BENHNHANID")
                or ""
            ),
            tiep_nhan_id=str(
                cls._get_case_insensitive(info_data, "TIEPNHANID")
                or cls._get_case_insensitive(search_data, "TIEPNHANID")
                or ""
            ),
            kham_benh_id=str(
                cls._get_case_insensitive(info_data, "KHAMBENHID")
                or cls._get_case_insensitive(search_data, "KHAMBENHID")
                or ""
            ),
            mau_benh_pham_id=str(
                cls._get_case_insensitive(search_data, "MAUBENHPHAMID") or ""
            ),
            ho_so_benh_an_id=str(
                cls._get_case_insensitive(info_data, "HOSOBENHANID")
                or cls._get_case_insensitive(search_data, "HOSOBENHANID")
                or ""
            ),
        )

        services = []
        for svc in services_data:
            if not isinstance(svc, dict):
                continue
            name = cls._get_case_insensitive(svc, "TENDICHVU")
            if name:
                services.append(
                    ServiceInfo(
                        code=str(cls._get_case_insensitive(svc, "MADICHVU", "")),
                        name=str(name),
                        note=str(cls._get_case_insensitive(svc, "GHICHUCD", "")),
                        status=str(cls._get_case_insensitive(svc, "TRANGTHAIDICHVU", "")),
                    )
                )

        return PatientInfo(
            patient_code=barcode,
            patient_name=patient_name,
            age=age,
            gender=gender,
            address=address,
            his=his_ids,
            services=services,
        )

    @staticmethod
    def _build_minimal_patient(
        barcode: str,
        search_data: dict[str, Any],
    ) -> PatientInfo:
        """Tạo PatientInfo tối thiểu khi không tìm được MAUBENHPHAMID."""
        return PatientInfo(
            patient_code=barcode,
            patient_name=str(search_data.get("TENBENHNHAN", "")),
            age=int(search_data.get("TUOI", 0) or 0),
            gender=str(search_data.get("GIOITINH", "")),
            address=str(search_data.get("DIACHI", "")),
            services=[],
        )
