"""
Config Manager สำหรับระบบ NUMediaBooth
======================================
รับผิดชอบการอ่านและเขียนไฟล์ config.json 
เพื่อเก็บการตั้งค่าของโปรแกรมให้คงอยู่เมื่อเปิดปิดแอปใหม่
"""

import os
import json
import logging
from path_manager import get_dynamic_path

logger = logging.getLogger(__name__)


class ConfigManager:
    """คลาสจัดการไฟล์การตั้งค่า (config.json)"""
    
    DEFAULT_CONFIG = {
        "export_path": "",
        "gdrive_folder_id": "",
        "printer_name": "",
        "camera_name": "",
        "admin_password": "1234"
    }

    def __init__(self, config_path: str = None) -> None:
        if config_path is None:
            self.config_path = get_dynamic_path(os.path.join("saveSetting", "config.json"))
        else:
            self.config_path = os.path.abspath(config_path)
            
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        self.config = self.DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> None:
        """อ่านข้อมูลจาก config.json หากไม่มีให้ใช้ค่าตั้งต้น"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # อัปเดตข้อมูลทับค่าเริ่มต้น (เผื่อในอนาคตมีคีย์ใหม่ๆ จะได้ไม่แครช)
                    self.config.update(data)
                logger.info("โหลดการตั้งค่าสำเร็จจาก: %s", self.config_path)
            except Exception as e:
                logger.error("อ่านไฟล์ Config ผิดพลาด (ใช้ค่าตั้งต้นแทน): %s", e)
        else:
            logger.info("ไม่พบไฟล์ Config สร้างใหม่ที่: %s", self.config_path)
            self.save()

    def save(self) -> None:
        """เขียนข้อมูลการตั้งค่าปัจจุบันลง config.json"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info("บันทึกการตั้งค่าลงไฟล์เรียบร้อย")
        except Exception as e:
            logger.error("เซฟไฟล์ Config ผิดพลาด: %s", e)

    def get(self, key: str, default=None):
        """ดึงค่าคอนฟิก"""
        return self.config.get(key, default)

    def set(self, key: str, value) -> None:
        """ตั้งค่าคอนฟิก 1 ตัว และเซฟทันที"""
        self.config[key] = value
        self.save()

    def update(self, new_config: dict) -> None:
        """อัปเดตค่าคอนฟิกหลายตัวพร้อมกัน และเซฟ"""
        self.config.update(new_config)
        self.save()

    def get_all(self) -> dict:
        """ดึงค่าคอนฟิกทั้งหมดเพื่อส่งให้ UI"""
        return self.config.copy()
