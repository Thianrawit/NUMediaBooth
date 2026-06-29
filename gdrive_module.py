import os
import time
import base64
import requests
import logging
from PyQt6.QtCore import QThread, pyqtSignal

from logger_setup import save_crash_dump

logger = logging.getLogger(__name__)

GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbzQ2G4bDqCR-B0iMXXRgXWTSuE1GFLrxBwaLbItWcGHxLg-Fnxya-BNnJ7TmSLIsvqw/exec"  # <-- ใส่ Web App URL กลางที่นี่

class GoogleDriveUploadThread(QThread):
    """
    เธรดสำหรับอัปโหลดภาพไป Google Drive ผ่าน Google Apps Script (Web App)
    ไม่ทำให้ UI หลักค้าง
    """
    upload_success = pyqtSignal(str)  # ส่ง URL รูปกลับมา
    upload_failed = pyqtSignal(str)   # ส่งข้อความ Error กลับมา

    def __init__(self, file_path: str, folder_id: str) -> None:
        super().__init__()
        self.file_path = file_path
        self.folder_id = folder_id

    def run(self) -> None:
        try:
            if not os.path.exists(self.file_path):
                self.upload_failed.emit(f"ไม่พบไฟล์: {self.file_path}")
                return
                
            if not GAS_WEBAPP_URL.startswith("http"):
                self.upload_failed.emit(f"URL ไม่ถูกต้อง กรุณาตั้งค่า GAS_WEBAPP_URL ใน gdrive_module.py")
                return
                
            logger.info("เริ่มอัปโหลดไฟล์ %s ไปยัง Google Drive ผ่าน Web App", self.file_path)
            
            with open(self.file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                
            filename = os.path.basename(self.file_path)
            
            payload = {
                "image": encoded_string,
                "folder_id": self.folder_id,
                "filename": filename
            }
            
            # ส่ง POST request ไปที่ Google Apps Script
            response = requests.post(GAS_WEBAPP_URL, json=payload, timeout=60)
            response.raise_for_status()
            
            # อ่านผลลัพธ์
            result = response.json()
            if result.get("status") == "success":
                file_url = result.get("url", "")
                logger.info("อัปโหลดสำเร็จ: %s", file_url)
                self.upload_success.emit(file_url)
            else:
                err_msg = result.get("message", "Unknown error from GAS")
                logger.error("อัปโหลดไม่สำเร็จ (GAS Error): %s", err_msg)
                self.upload_failed.emit(err_msg)

        except Exception as e:
            logger.error("เกิดข้อผิดพลาดในการอัปโหลดรูป: %s", e)
            save_crash_dump(self.file_path, "gdrive_upload_failed")
            self.upload_failed.emit(str(e))
