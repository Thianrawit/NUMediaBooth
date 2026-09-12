import os
import sys
import shutil
import hashlib
import logging
import subprocess
import ctypes
from pathlib import Path

import requests
from packaging import version

from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication
from PyQt6.QtCore import Qt, QThread, pyqtSignal

logger = logging.getLogger(__name__)

CURRENT_VERSION = "v1.6"
API_URL = "https://api.github.com/repos/Thianrawit/NUMediaBooth/releases/latest"

# GitHub บังคับว่าต้องมี User-Agent ไม่งั้นบางทีโดน reject เฉยๆ แบบงงๆ
REQUEST_HEADERS = {
    "User-Agent": "NUMediaBooth-AutoUpdater",
    "Accept": "application/vnd.github+json",
}

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2  # จะกลายเป็น 2, 4, 8 วิ ตามรอบ (exponential backoff)
MIN_FREE_SPACE_BUFFER_MB = 200  # กันเผื่อพื้นที่ดิสก์ เผื่อไฟล์อื่นโตระหว่างโหลด


def get_documents_path(folder_name="NumediaBooth"):
    """หา Path Documents ของเครื่อง user แล้วสร้างโฟลเดอร์ย่อยถ้ายังไม่มี"""
    docs_path = Path.home() / "Documents" / folder_name
    try:
        docs_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error("ไม่สามารถสร้างโฟลเดอร์ %s ได้: %s", docs_path, e)
        raise
    return str(docs_path)


def check_disk_space(path: str, required_bytes: int) -> bool:
    """เช็คว่าพื้นที่ดิสก์เหลือพอสำหรับไฟล์ + buffer กันพลาดมั้ย"""
    try:
        free_bytes = shutil.disk_usage(path).free
        required_with_buffer = required_bytes + (MIN_FREE_SPACE_BUFFER_MB * 1024 * 1024)
        return free_bytes >= required_with_buffer
    except OSError as e:
        logger.error("เช็คพื้นที่ดิสก์ไม่ได้: %s", e)
        # เช็คไม่ได้ ให้ผ่านไปก่อน (fail-open) ดีกว่าบล็อคผู้ใช้เฉยๆ
        return True


def check_write_permission(path: str) -> bool:
    """เช็คว่าเขียนไฟล์ในโฟลเดอร์นี้ได้จริงมั้ย ก่อนจะเริ่มโหลดยาวๆ"""
    test_file = os.path.join(path, ".write_test_tmp")
    try:
        with open(test_file, "wb") as f:
            f.write(b"test")
        os.remove(test_file)
        return True
    except OSError as e:
        logger.error("ไม่มีสิทธิ์เขียนไฟล์ที่ %s: %s", path, e)
        return False


def verify_sha256(file_path: str, expected_hash: str) -> bool:
    """เทียบ SHA256 ของไฟล์ที่โหลดมา กับ hash ที่ GitHub ให้มา (ถ้ามี)"""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual_hash = sha256.hexdigest().lower()
        return actual_hash == expected_hash.lower().strip()
    except OSError as e:
        logger.error("เปิดไฟล์เพื่อเช็ค hash ไม่ได้: %s", e)
        return False


def cleanup_old_installers(temp_dir: str):
    """ลบไฟล์ .exe ค้างจากรอบก่อนหน้าที่โหลดไม่สำเร็จ / ยังไม่ถูกลบ"""
    try:
        for f in Path(temp_dir).glob("*.exe"):
            try:
                f.unlink()
                logger.info("ลบไฟล์ installer เก่าทิ้ง: %s", f)
            except OSError:
                # ไฟล์อาจถูกใช้งานอยู่ ข้ามไปเฉยๆ ไม่ต้อง crash
                pass
    except OSError as e:
        logger.warning("cleanup_old_installers ล้มเหลว: %s", e)


# ==========================================
# 1. Thread สำหรับเช็คเวอร์ชัน (มี Retry + Rate limit handling)
# ==========================================
class CheckUpdateWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str, str)  # (error_type, message) แยกประเภท error ให้ UI ตัดสินใจง่ายขึ้น

    def run(self):
        import time

        last_exception_msg = ""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(API_URL, headers=REQUEST_HEADERS, timeout=10)

                if response.status_code == 403:
                    # โดน GitHub API Rate Limit
                    reset_header = response.headers.get("X-RateLimit-Reset", "")
                    self.error.emit(
                        "rate_limit",
                        f"โดน GitHub Rate Limit ชั่วคราว (reset: {reset_header})",
                    )
                    return

                response.raise_for_status()

                try:
                    data = response.json()
                except ValueError as e:
                    self.error.emit("invalid_response", f"GitHub ตอบข้อมูลที่ parse ไม่ได้: {e}")
                    return

                self.finished.emit(data)
                return

            except requests.exceptions.Timeout:
                last_exception_msg = "การเชื่อมต่อหมดเวลา (timeout)"
            except requests.exceptions.ConnectionError:
                last_exception_msg = "เชื่อมต่ออินเทอร์เน็ตไม่ได้"
            except requests.exceptions.RequestException as e:
                last_exception_msg = str(e)

            # ยังไม่ครบรอบ retry ให้รอแล้วลองใหม่ (exponential backoff)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        self.error.emit("network", f"เชื่อมต่อไม่สำเร็จหลังลอง {MAX_RETRIES} ครั้ง: {last_exception_msg}")


# ==========================================
# 2. Thread สำหรับดาวน์โหลดไฟล์ติดตั้ง (มี integrity check + indeterminate progress)
# ==========================================
class DownloadWorker(QThread):
    progress = pyqtSignal(int)  # -1 หมายถึง "ไม่รู้เปอร์เซ็นต์" ให้ UI เปลี่ยนเป็น indeterminate mode
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, download_url, save_path, expected_size=0, expected_sha256=None):
        super().__init__()
        self.download_url = download_url
        self.save_path = save_path
        self.expected_size = expected_size
        self.expected_sha256 = expected_sha256
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            response = requests.get(
                self.download_url, headers=REQUEST_HEADERS, stream=True, timeout=15
            )
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0)) or self.expected_size

            downloaded = 0
            with open(self.save_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._is_cancelled:
                        logger.info("ผู้ใช้ยกเลิกการดาวน์โหลด")
                        file.close()
                        self._safe_remove_partial_file()
                        return
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            self.progress.emit(downloaded)
                        else:
                            # ไม่รู้ขนาดไฟล์ทั้งหมด บอก UI ให้ทำ indeterminate bar แทน
                            self.progress.emit(-1)

            # เช็คว่าขนาดไฟล์ที่โหลดมาตรงกับที่ควรจะเป็นมั้ย (กันโหลดขาด)
            if total_size > 0 and downloaded < total_size:
                self.error.emit(
                    f"ดาวน์โหลดไม่ครบ ({downloaded}/{total_size} bytes) ไฟล์อาจเสียหาย"
                )
                self._safe_remove_partial_file()
                return

            # เช็ค checksum ถ้ามีการแนบ hash มาด้วย
            if self.expected_sha256:
                if not verify_sha256(self.save_path, self.expected_sha256):
                    self.error.emit("ไฟล์ที่โหลดมาไม่ผ่านการตรวจสอบ checksum (อาจถูกดัดแปลง)")
                    self._safe_remove_partial_file()
                    return
                logger.info("ตรวจสอบ SHA256 ผ่าน — ไฟล์ปลอดภัย")
            else:
                logger.warning("ไม่มี checksum ให้ตรวจสอบ — ข้ามขั้นตอนนี้ (ควรพิจารณาแนบ .sha256 ใน release ครั้งหน้า)")

            self.finished.emit(self.save_path)

        except requests.exceptions.Timeout:
            self.error.emit("การดาวน์โหลดหมดเวลา (timeout) กรุณาลองใหม่")
            self._safe_remove_partial_file()
        except requests.exceptions.ConnectionError:
            self.error.emit("การเชื่อมต่ออินเทอร์เน็ตขาดหายระหว่างดาวน์โหลด")
            self._safe_remove_partial_file()
        except OSError as e:
            # เช่น ดิสก์เต็มกลางทาง, ไม่มีสิทธิ์เขียนไฟล์
            self.error.emit(f"เขียนไฟล์ลงดิสก์ไม่ได้: {e}")
            self._safe_remove_partial_file()
        except Exception as e:
            logger.exception("Unexpected download error")
            self.error.emit(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")
            self._safe_remove_partial_file()

    def _safe_remove_partial_file(self):
        """ลบไฟล์ที่โหลดค้างไว้ครึ่งๆ กลางๆ ทิ้ง กันเปิดผิดโดยไม่ตั้งใจ"""
        try:
            if os.path.exists(self.save_path):
                os.remove(self.save_path)
        except OSError:
            pass


# ==========================================
# 3. ตัวจัดการหลัก (AutoUpdater)
# ==========================================
class AutoUpdater:
    def __init__(self, parent_widget=None):
        self.parent_widget = parent_widget
        self.progress_dialog = None
        self.check_worker = None
        self.download_worker = None
        self._is_checking = False
        self._is_downloading = False

    # ---------- เช็คอัปเดต ----------

    def check_for_updates(self, silent_if_error: bool = False):
        """
        เช็คเวอร์ชันด้วย Thread
        silent_if_error: ถ้า True จะไม่โชว์ popup error (ใช้เวลาเช็คอัตโนมัติตอนเปิดโปรแกรม
                          เพื่อไม่ให้ user เห็น error รก ๆ ตั้งแต่เปิดแอป)
        """
        if self._is_checking:
            logger.info("กำลังเช็คอัปเดตอยู่แล้ว ข้ามคำสั่งซ้ำ")
            return
        if self._is_downloading:
            logger.info("กำลังดาวน์โหลดอัปเดตอยู่ ไม่เช็คซ้ำ")
            return

        self._is_checking = True
        self._silent_check = silent_if_error

        self.check_worker = CheckUpdateWorker()
        self.check_worker.finished.connect(self._on_check_finished)
        self.check_worker.error.connect(self._on_check_error)
        self.check_worker.finished.connect(lambda _=None: setattr(self, "_is_checking", False))
        self.check_worker.error.connect(lambda *_: setattr(self, "_is_checking", False))
        self.check_worker.start()

    def _on_check_finished(self, data: dict):
        latest_version = data.get("tag_name", "")

        try:
            current_v = CURRENT_VERSION.lstrip("vV")
            latest_v = latest_version.lstrip("vV")
            is_newer = latest_version and version.parse(latest_v) > version.parse(current_v)
        except version.InvalidVersion as e:
            logger.error("รูปแบบเวอร์ชันไม่ถูกต้อง parse ไม่ได้: %s", e)
            if not self._silent_check:
                QMessageBox.warning(
                    self.parent_widget, "ข้อผิดพลาด",
                    "รูปแบบเวอร์ชันจาก GitHub ไม่ถูกต้อง ไม่สามารถเปรียบเทียบได้"
                )
            return

        if is_newer:
            body_info = data.get("body", "ไม่มีรายละเอียดการอัปเดต")

            download_url = ""
            total_size = 0
            exe_name = ""
            sha256_hash = None

            assets = data.get("assets", [])
            for asset in assets:
                name = asset.get("name", "")
                if name.endswith(".exe"):
                    download_url = asset.get("browser_download_url")
                    total_size = asset.get("size", 0)
                    exe_name = name

            # หา checksum file แนบ (ถ้า release มีไฟล์ .sha256 คู่กับ .exe)
            if exe_name:
                for asset in assets:
                    if asset.get("name", "") == f"{exe_name}.sha256":
                        try:
                            sha_resp = requests.get(
                                asset.get("browser_download_url"),
                                headers=REQUEST_HEADERS,
                                timeout=10,
                            )
                            sha_resp.raise_for_status()
                            sha256_hash = sha_resp.text.strip().split()[0]
                        except (requests.exceptions.RequestException, IndexError) as e:
                            logger.warning("โหลด checksum file ไม่สำเร็จ: %s", e)

            if not download_url:
                QMessageBox.warning(
                    self.parent_widget, "อัปเดต",
                    "มีอัปเดตใหม่ แต่ไม่พบไฟล์ติดตั้ง (.exe) ใน GitHub Release"
                )
                return

            reply = QMessageBox.question(
                self.parent_widget,
                "มีอัปเดตใหม่!",
                f"เวอร์ชัน {latest_version} พร้อมใช้งานแล้ว\n\n"
                f"รายละเอียด:\n{body_info}\n\n"
                f"ต้องการอัปเดตตอนนี้เลยหรือไม่?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.start_download(download_url, total_size, sha256_hash)

    def _on_check_error(self, error_type: str, error_msg: str):
        logger.error("Check Update Error [%s]: %s", error_type, error_msg)

        if self._silent_check:
            # เช็คอัตโนมัติตอนเปิดแอป ไม่ต้องรบกวน user ด้วย popup
            return

        friendly_messages = {
            "rate_limit": "เซิร์ฟเวอร์ปฏิเสธคำขอชั่วคราว (Rate Limit) กรุณาลองใหม่ภายหลัง",
            "invalid_response": "ข้อมูลจากเซิร์ฟเวอร์ไม่ถูกต้อง กรุณาลองใหม่",
            "network": "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์อัปเดตได้ กรุณาตรวจสอบอินเทอร์เน็ต",
        }
        message = friendly_messages.get(error_type, f"เกิดข้อผิดพลาด: {error_msg}")
        QMessageBox.warning(self.parent_widget, "ข้อผิดพลาด", message)

    # ---------- ดาวน์โหลด ----------

    def start_download(self, download_url: str, total_size: int, sha256_hash: str = None):
        """เริ่มดาวน์โหลดไฟล์ด้วย Thread พร้อมเช็ค pre-condition ทุกอย่างก่อน"""
        if self._is_downloading:
            logger.info("กำลังดาวน์โหลดอยู่แล้ว ข้ามคำสั่งซ้ำ")
            return

        try:
            temp_dir = get_documents_path("temp")
        except OSError:
            QMessageBox.critical(
                self.parent_widget, "ข้อผิดพลาด",
                "ไม่สามารถสร้างโฟลเดอร์สำหรับดาวน์โหลดได้ กรุณาตรวจสอบสิทธิ์การเข้าถึง"
            )
            return

        cleanup_old_installers(temp_dir)

        if not check_write_permission(temp_dir):
            QMessageBox.critical(
                self.parent_widget, "ข้อผิดพลาด",
                f"ไม่มีสิทธิ์เขียนไฟล์ในโฟลเดอร์:\n{temp_dir}\n"
                "กรุณาตรวจสอบสิทธิ์การเข้าถึง หรือรันโปรแกรมในสิทธิ์ที่สูงขึ้น"
            )
            return

        if total_size > 0 and not check_disk_space(temp_dir, total_size):
            QMessageBox.critical(
                self.parent_widget, "พื้นที่ดิสก์ไม่พอ",
                f"พื้นที่ดิสก์เหลือไม่พอสำหรับดาวน์โหลด (ต้องการอย่างน้อย "
                f"{(total_size + MIN_FREE_SPACE_BUFFER_MB * 1024 * 1024) / (1024*1024):.0f} MB)\n"
                "กรุณาลบไฟล์บางส่วนแล้วลองใหม่"
            )
            return

        save_path = os.path.join(temp_dir, "NUMediaBooth_Updater.exe")
        self._is_downloading = True

        self.progress_dialog = QProgressDialog(
            "กำลังดาวน์โหลดอัปเดต...", "ยกเลิก", 0, max(total_size, 1), self.parent_widget
        )
        self.progress_dialog.setWindowTitle("อัปเดตโปรแกรม")
        self.progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()

        self.download_worker = DownloadWorker(
            download_url, save_path, expected_size=total_size, expected_sha256=sha256_hash
        )
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)
        self.progress_dialog.canceled.connect(self._on_user_cancel_download)

        self.download_worker.start()

    def _on_download_progress(self, value: int):
        if not self.progress_dialog:
            return
        if value == -1:
            # ไม่รู้ขนาดไฟล์ทั้งหมด → เปลี่ยนเป็น indeterminate mode (bar วิ่งไปเรื่อยๆ)
            self.progress_dialog.setMaximum(0)
            self.progress_dialog.setLabelText("กำลังดาวน์โหลดอัปเดต... (ไม่ทราบขนาดไฟล์)")
        else:
            self.progress_dialog.setValue(value)

    def _on_user_cancel_download(self):
        if self.download_worker:
            self.download_worker.cancel()
        self._is_downloading = False
        logger.info("ผู้ใช้กดยกเลิกการดาวน์โหลด")

    def _on_download_finished(self, save_path: str):
        self._is_downloading = False
        if self.progress_dialog:
            self.progress_dialog.close()

        logger.info("ดาวน์โหลดเสร็จสิ้น รันตัวติดตั้ง: %s", save_path)

        # เช็คพื้นที่ดิสก์ปลายทาง (install dir) ด้วย ไม่ใช่แค่ temp
        install_dir = self._get_current_install_dir()
        if install_dir:
            installer_size = os.path.getsize(save_path)
            estimated_extracted = installer_size * 3
            if not check_disk_space(install_dir, estimated_extracted):
                QMessageBox.critical(
                    self.parent_widget, "พื้นที่ดิสก์ไม่พอ",
                    f"พื้นที่ดิสก์ที่โฟลเดอร์ติดตั้ง ({install_dir}) ไม่เพียงพอ\n"
                    f"ต้องการอย่างน้อย {estimated_extracted / (1024*1024):.0f} MB\n\n"
                    "กรุณาลบไฟล์ที่ไม่จำเป็นแล้วลองใหม่"
                )
                return

        try:
            # 🔥 รัน installer แบบ DETACHED ให้ทำงานอิสระจาก parent process
            # /SILENT = ติดตั้งอัตโนมัติ, /CLOSEAPPLICATIONS = ปิดโปรแกรมตัวเก่า
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                [save_path, '/SILENT', '/CLOSEAPPLICATIONS'],
                creationflags=DETACHED_PROCESS,
                close_fds=True,
            )
        except OSError as e:
            logger.error("รันตัวติดตั้งไม่สำเร็จ: %s", e)
            QMessageBox.critical(
                self.parent_widget, "ข้อผิดพลาด",
                f"ดาวน์โหลดเสร็จแล้ว แต่รันตัวติดตั้งไม่สำเร็จ:\n{e}\n\n"
                f"กรุณาเปิดไฟล์ด้วยตนเองที่:\n{save_path}"
            )
            return

        # ⚡ ปิดแอปทันทีเลย ไม่ต้องรอ user กดอะไร
        # เพื่อปลดล็อคไฟล์ให้ installer ทำงานได้โดยไม่ error
        logger.info("ปิดแอปทันทีเพื่อให้ installer ทำงาน...")
        QApplication.quit()
        sys.exit(0)

    def _get_current_install_dir(self) -> str:
        """หา path โฟลเดอร์ที่โปรแกรมถูกติดตั้งอยู่ (สำหรับเช็คพื้นที่ดิสก์)"""
        try:
            if getattr(sys, 'frozen', False):
                return os.path.dirname(sys.executable)
            else:
                return os.path.dirname(os.path.abspath(__file__))
        except Exception:
            return ""

    def _on_download_error(self, error_msg: str):
        self._is_downloading = False
        if self.progress_dialog:
            self.progress_dialog.close()
        logger.error("Download Error: %s", error_msg)
        QMessageBox.critical(
            self.parent_widget, "ข้อผิดพลาด",
            f"การดาวน์โหลดล้มเหลว: {error_msg}\n\nกรุณาลองใหม่อีกครั้ง"
        )