import os
import sys
import tarfile
import gzip
import io
import time
from pathlib import Path

# =============================================================================
# DEBIAN PACKAGE BUILDER (.deb) FOR AUTOQ ADMIN CENTER (UBUNTU 26.04 / LINUX)
# =============================================================================

def create_ar_header(filename: str, size: int, mtime=None) -> bytes:
    if mtime is None:
        mtime = int(time.time())
    fn = filename.ljust(16)[:16].encode('ascii')
    ts = str(mtime).ljust(12)[:12].encode('ascii')
    owner = "0".ljust(6)[:6].encode('ascii')
    group = "0".ljust(6)[:6].encode('ascii')
    mode = "100644".ljust(8)[:8].encode('ascii')
    sz = str(size).ljust(10)[:10].encode('ascii')
    fmag = b"\x60\x0a"
    return fn + ts + owner + group + mode + sz + fmag

def create_ar_entry(filename: str, data: bytes, mtime=None) -> bytes:
    header = create_ar_header(filename, len(data), mtime)
    padding = b"\n" if (len(data) % 2 != 0) else b""
    return header + data + padding

def build_deb_package(root_dir=r"d:\AUTOQ"):
    print("=== BUILDING DEBIAN PACKAGE (.deb) FOR AUTOQ ADMIN CENTER (UBUNTU 26.04) ===")
    
    pkg_name = "autoq-admin"
    version = "4.0-1"
    arch = "amd64"
    deb_filename = f"{pkg_name}_{version}_{arch}.deb"
    output_dir = os.path.join(root_dir, "installer")
    os.makedirs(output_dir, exist_ok=True)
    deb_filepath = os.path.join(output_dir, deb_filename)

    # 1. Prepare debian-binary
    debian_binary = b"2.0\n"

    # 2. Build control.tar.gz
    buf_control = io.BytesIO()
    with tarfile.open(fileobj=buf_control, mode="w:gz") as tar:
        # DEBIAN/control
        control_content = f"""Package: {pkg_name}
Version: {version}
Section: utils
Priority: optional
Architecture: {arch}
Maintainer: Khoa Chan Doan Hinh Anh - BVDK Ky Anh <admin@autoq.local>
Depends: python3 (>= 3.10), python3-pyside6, python3-google-api-core, python3-yaml, python3-requests
Description: AutoQ Radiology Admin & Reporting Center (Ubuntu 26.04 / Linux)
 AutoQ Admin Center for real-time ultrasound rooms monitoring,
 patient throughput tracking, examination time metrics, and end-of-day reporting.
 Applied at Khoa Chan Doan Hinh Anh - BVDK Tx Ky Anh.
""".encode('utf-8')

        ti_ctrl = tarfile.TarInfo(name="./control")
        ti_ctrl.size = len(control_content)
        ti_ctrl.mode = 0o644
        ti_ctrl.mtime = int(time.time())
        tar.addfile(ti_ctrl, io.BytesIO(control_content))

        # DEBIAN/postinst
        postinst_content = b"""#!/bin/bash
set -e
chmod +x /usr/bin/autoq-admin
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q || true
fi
echo "AutoQ Admin Center v4.0 for Ubuntu 26.04 installed successfully!"
exit 0
"""
        ti_post = tarfile.TarInfo(name="./postinst")
        ti_post.size = len(postinst_content)
        ti_post.mode = 0o755
        ti_post.mtime = int(time.time())
        tar.addfile(ti_post, io.BytesIO(postinst_content))

        # DEBIAN/prerm
        prerm_content = b"""#!/bin/bash
set -e
exit 0
"""
        ti_prerm = tarfile.TarInfo(name="./prerm")
        ti_prerm.size = len(prerm_content)
        ti_prerm.mode = 0o755
        ti_prerm.mtime = int(time.time())
        tar.addfile(ti_prerm, io.BytesIO(prerm_content))

    control_tar_gz = buf_control.getvalue()

    # 3. Build data.tar.gz
    buf_data = io.BytesIO()
    with tarfile.open(fileobj=buf_data, mode="w:gz") as tar:
        # Launcher script: /usr/bin/autoq-admin
        launcher_code = b"""#!/bin/bash
export PYTHONPATH=/usr/lib/autoq-admin:$PYTHONPATH
exec python3 /usr/lib/autoq-admin/admin_app.py "$@"
"""
        ti_launch = tarfile.TarInfo(name="./usr/bin/autoq-admin")
        ti_launch.size = len(launcher_code)
        ti_launch.mode = 0o755
        ti_launch.mtime = int(time.time())
        tar.addfile(ti_launch, io.BytesIO(launcher_code))

        # Desktop Entry: /usr/share/applications/autoq-admin.desktop
        desktop_entry = b"""[Desktop Entry]
Name=AutoQ Admin Center
Comment=Qu\xc3\xa1n tr\xe1\xbb\x8b & B\xc3\xa1o c\xc3\xa1o Realtime Khoa C\xc4\x90HA (Ubuntu 26.04)
Exec=/usr/bin/autoq-admin
Icon=/usr/lib/autoq-admin/hospital.ico
Terminal=false
Type=Application
Categories=Medical;Office;Utility;
Keywords=autoq;radiology;ultrasound;admin;reporting;
"""
        ti_desk = tarfile.TarInfo(name="./usr/share/applications/autoq-admin.desktop")
        ti_desk.size = len(desktop_entry)
        ti_desk.mode = 0o644
        ti_desk.mtime = int(time.time())
        tar.addfile(ti_desk, io.BytesIO(desktop_entry))

        # Source code files to include in /usr/lib/autoq-admin/
        source_files = [
            "admin_app.py",
            "firestore_queue.py",
            "firestore_client.py",
            "config_manager.py",
            "hospital.ico"
        ]

        for fname in source_files:
            fpath = os.path.join(root_dir, fname)
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    content = f.read()
                ti_file = tarfile.TarInfo(name=f"./usr/lib/autoq-admin/{fname}")
                ti_file.size = len(content)
                ti_file.mode = 0o644
                ti_file.mtime = int(time.time())
                tar.addfile(ti_file, io.BytesIO(content))

    data_tar_gz = buf_data.getvalue()

    # 4. Assemble final .deb ar archive
    deb_header = b"!<arch>\n"
    e1 = create_ar_entry("debian-binary", debian_binary)
    e2 = create_ar_entry("control.tar.gz", control_tar_gz)
    e3 = create_ar_entry("data.tar.gz", data_tar_gz)

    final_deb_bytes = deb_header + e1 + e2 + e3

    with open(deb_filepath, "wb") as f:
        f.write(final_deb_bytes)

    print(f"[SUCCESS] Created Debian package (.deb) successfully: {deb_filepath}")
    print(f"File Size: {len(final_deb_bytes)} bytes (~{round(len(final_deb_bytes)/1024, 1)} KB)")
    return deb_filepath

if __name__ == "__main__":
    build_deb_package()
