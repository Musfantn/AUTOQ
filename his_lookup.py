# =============================================================================
# FILE: his_lookup.py
# MÔ TẢ: Module dùng chung cho logic tra cứu thông tin bệnh nhân từ VNPT HIS
#        bằng Selenium WebDriver qua cổng debug 9222.
# =============================================================================

import os
import time
import socket
import subprocess
from datetime import datetime
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    webdriver = None

def tinh_tuoi(ngay_sinh_str):
    """Tính tuổi từ chuỗi ngày sinh."""
    try:
        ngay_sinh_str = ngay_sinh_str.strip()
        if not ngay_sinh_str:
            return 0
        date_part = ngay_sinh_str.split()[0]
        if "/" in date_part:
            birth_year = int(date_part.split("/")[-1])
        elif "-" in date_part:
            birth_year = int(date_part.split("-")[0])
        else:
            birth_year = int(date_part)
        current_year = datetime.now().year
        return current_year - birth_year
    except Exception:
        return 0

def is_port_open(port):
    """Kiểm tra cổng TCP có mở không."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def open_chrome_debug():
    """Tự động mở Chrome ở chế độ remote debugging port 9222."""
    if is_port_open(9222):
        return True
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]
    chrome_path = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_path = path
            break
    if not chrome_path:
        return False
    user_data_dir = r"C:\ChromeDebug"
    os.makedirs(user_data_dir, exist_ok=True)
    try:
        subprocess.Popen(
            [chrome_path, "--remote-debugging-port=9222", f"--user-data-dir={user_data_dir}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(2.5)
        return True
    except Exception:
        return False

def perform_his_lookup(driver, ma_bn):
    """Thực hiện tra cứu bệnh nhân trên trang VNPT HIS đang mở bằng Selenium."""
    wait = WebDriverWait(driver, 5)
    
    # 1. Tìm ô tìm kiếm và nhập mã bệnh nhân
    search_box = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Nhập thông tin phiếu chỉ định để tìm kiếm']"))
    )
    search_box.clear()
    search_box.send_keys(ma_bn)
    search_box.send_keys(Keys.ENTER)

    # 2. Đợi mã bệnh nhân hiển thị khớp ở dòng đầu bảng danh sách chỉ định
    def cho_ma_bn_khop(d):
        try:
            rows = d.find_elements(By.XPATH, "//table[@id='grdDanhSachCDHA']//tr[contains(@class, 'jqgrow')]")
            if not rows:
                return False
            cells = rows[0].find_elements(By.TAG_NAME, "td")
            if len(cells) >= 6:
                return cells[5].text.strip().upper() == ma_bn.upper()
            return False
        except Exception:
            return False

    wait.until(cho_ma_bn_khop)

    # 3. Lấy thông tin họ tên, ngày sinh, tuổi từ bảng danh sách
    rows = driver.find_elements(By.XPATH, "//table[@id='grdDanhSachCDHA']//tr[contains(@class, 'jqgrow')]")
    ten_bn = ""
    ngay_sinh = ""
    tuoi = ""
    matching_indices = []

    for i, row in enumerate(rows):
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 6 and cells[5].text.strip().upper() == ma_bn.upper():
                matching_indices.append(i + 1)
                if not ten_bn and len(cells) >= 9:
                    ten_bn = cells[7].text.strip()
                    ngay_sinh = cells[8].text.strip()
                    tuoi = str(tinh_tuoi(ngay_sinh))
        except Exception:
            pass

    # Dự phòng nếu không tìm thấy chỉ chỉ định khớp nhưng có dòng
    if not matching_indices:
        if rows:
            cells = rows[0].find_elements(By.TAG_NAME, "td")
            if len(cells) >= 9:
                ten_bn = cells[7].text.strip()
                ngay_sinh = cells[8].text.strip()
                tuoi = str(tinh_tuoi(ngay_sinh))
            matching_indices = [1]

    # 4. Quét các dịch vụ chỉ định từ bảng chi tiết kết quả chẩn đoán
    dich_vu_list = []
    dich_vu_xpath = "//table[@id='grdKetQuaChanDoan']//tr[contains(@class, 'jqgrow')]"
    
    for idx in matching_indices:
        try:
            row = driver.find_element(By.XPATH, f"//table[@id='grdDanhSachCDHA']//tr[contains(@class, 'jqgrow')][{idx}]")
            try:
                row.click()
            except Exception:
                driver.execute_script("arguments[0].click();", row)
            
            time.sleep(0.5)
            
            service_rows = driver.find_elements(By.XPATH, dich_vu_xpath)
            for s_row in service_rows:
                s_cells = s_row.find_elements(By.TAG_NAME, "td")
                if len(s_cells) >= 4:
                    s_name = s_cells[3].text.strip()
                    if s_name and s_name not in dich_vu_list:
                        dich_vu_list.append(s_name)
        except Exception:
            pass

    return ten_bn, ngay_sinh, tuoi, dich_vu_list
