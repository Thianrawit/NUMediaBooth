import os
import sys
import requests
import subprocess
import logging
from packaging import version

from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication
from PyQt6.QtCore import Qt, QThread, pyqtSignal

logger = logging.getLogger(__name__)

CURRENT_VERSION = "v1.4"
API_URL = "https://api.github.com/repos/Thianrawit/NUMediaBooth/releases/latest"

def get_documents_path(folder_name="NumediaBooth"):
    # ฟังก์ชันหา Path Documents ของมึง
    from pathlib import Path
    docs_path = Path.home() / "Documents" / folder_name
    if not docs_path.exists():
        docs_path.mkdir(parents=True, exist_ok=True)
    return str(docs_path)

# ==========================================
# 1. Thread สำหรับเช็คเวอร์ชัน (ไม่ให้แอปค้างตอนต่อเน็ต)
# ==========================================
class CheckUpdateWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def run(self):
        try:
            response = requests.get(API_URL, timeout=5)
            response.raise_for_status()
            self.finished.emit(response.json())
        except Exception as e:
            self.error.emit(str(e))

# ==========================================
# 2. Thread สำหรับดาวน์โหลดไฟล์ติดตั้ง
# ==========================================
class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, download_url, save_path):
        super().__init__()
        self.download_url = download_url
        self.save_path = save_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            response = requests.get(self.download_url, stream=True, timeout=10)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            
            downloaded = 0
            with open(self.save_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._is_cancelled:
                        logger.info("ผู้ใช้ยกเลิกการดาวน์โหลด")
                        return
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)
                        # โยนเปอร์เซ็นต์กลับไปที่ Main Thread แทนการใช้ processEvents()
                        if total_size > 0:
                            self.progress.emit(downloaded)
            
            # โหลดเสร็จ ส่งสัญญาณบอก
            self.finished.emit(self.save_path)
        except Exception as e:
            self.error.emit(str(e))

# ==========================================
# 3. ตัวจัดการหลัก (AutoUpdater)
# ==========================================
class AutoUpdater:
    def __init__(self, parent_widget=None):
        self.parent_widget = parent_widget
        self.progress_dialog = None

    def check_for_updates(self):
        """เช็คเวอร์ชันด้วย Thread"""
        self.check_worker = CheckUpdateWorker()
        self.check_worker.finished.connect(self._on_check_finished)
        self.check_worker.error.connect(self._on_check_error)
        self.check_worker.start()

    def _on_check_finished(self, data):
        latest_version = data.get("tag_name", "")
        current_v = CURRENT_VERSION.lstrip('vV')
        latest_v = latest_version.lstrip('vV')
        
        if latest_version and version.parse(latest_v) > version.parse(current_v):
            body_info = data.get("body", "ไม่มีรายละเอียดการอัปเดต")
            
            # หา URL ของตัวติดตั้ง (.exe) จาก GitHub Assets
            download_url = ""
            total_size = 0
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".exe"):
                    download_url = asset.get("browser_download_url")
                    total_size = asset.get("size", 0)
                    break
            
            if not download_url:
                QMessageBox.warning(self.parent_widget, "อัปเดต", "มีอัปเดตใหม่ แต่ไม่พบไฟล์ติดตั้ง (.exe) ใน GitHub")
                return

            reply = QMessageBox.question(
                self.parent_widget, 
                "มีอัปเดตใหม่!",
                f"เวอร์ชัน {latest_version} พร้อมใช้งานแล้ว\n\nรายละเอียด:\n{body_info}\n\nต้องการอัปเดตตอนนี้เลยหรือไม่?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.start_download(download_url, total_size)
        else:
            QMessageBox.information(self.parent_widget, "อัปเดต", "โปรแกรมของคุณเป็นเวอร์ชันล่าสุดแล้ว")

    def _on_check_error(self, error_msg):
        logger.error(f"Check Update Error: {error_msg}")
        QMessageBox.warning(self.parent_widget, "ข้อผิดพลาด", "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์อัปเดตได้")

    def start_download(self, download_url, total_size):
        """เริ่มดาวน์โหลดไฟล์ด้วย Thread"""
        temp_dir = get_documents_path("temp")
        save_path = os.path.join(temp_dir, "NUMediaBooth_Updater.exe")

        # สร้าง Dialog โง่ๆ ขึ้นมาอันนึง
        self.progress_dialog = QProgressDialog("กำลังดาวน์โหลดอัปเดต...", "ยกเลิก", 0, total_size, self.parent_widget)
        self.progress_dialog.setWindowTitle("อัปเดตโปรแกรม")
        self.progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.progress_dialog.setAutoClose(False)  # อย่าเพิ่งปิดจนกว่าจะสั่ง
        self.progress_dialog.show()

        # สร้างและสั่งรัน Worker
        self.download_worker = DownloadWorker(download_url, save_path)
        self.download_worker.progress.connect(self.progress_dialog.setValue)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)
        
        # ถ้ากดยกเลิก ให้ไปสั่งหยุด Thread
        self.progress_dialog.canceled.connect(self.download_worker.cancel)
        
        self.download_worker.start()

    def _on_download_finished(self, save_path):
        if self.progress_dialog:
            self.progress_dialog.close()
            
        logger.info(f"ดาวน์โหลดเสร็จสิ้น รันตัวติดตั้ง: {save_path}")
        QMessageBox.information(self.parent_widget, "สำเร็จ", "ดาวน์โหลดเสร็จสิ้น โปรแกรมจะปิดตัวลงเพื่อทำการติดตั้ง!")
        
        try:
            # สั่งรันไฟล์ Installer
            subprocess.Popen([save_path], shell=True)
        except Exception as e:
            logger.error(f"Failed to start installer: {e}")
            
        # ปิดโปรแกรมเพื่อหลีกทางให้ Installer
        QApplication.quit()
        sys.exit()

    def _on_download_error(self, error_msg):
        if self.progress_dialog:
            self.progress_dialog.close()
        logger.error(f"Download Error: {error_msg}")
        QMessageBox.critical(self.parent_widget, "ข้อผิดพลาด", "การดาวน์โหลดล้มเหลว กรุณาลองใหม่อีกครั้ง")