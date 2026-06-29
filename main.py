"""
NUMediaBooth — Photobooth Application
=======================================
Entry point ของโปรแกรม
"""

import sys
import os
import logging

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from ui import MainWindow
from logger_setup import setup_logger
from path_manager import get_dynamic_path, get_resource_path

def main() -> None:
    """จุดเริ่มต้นของโปรแกรม"""
    # สร้างโฟลเดอร์แบบ dynamic (เมื่อเป็น .exe จะสร้างโฟลเดอร์ข้างๆ .exe)
    os.makedirs(get_dynamic_path("logs"), exist_ok=True)
    os.makedirs(get_dynamic_path("saveSetting"), exist_ok=True)
    os.makedirs(get_dynamic_path(".NUMediaBooth_Temp"), exist_ok=True)

    setup_logger()
    logger = logging.getLogger(__name__)
    logger.info("เริ่มต้น NUMediaBooth...")

    # สร้างโฟลเดอร์ assets/templates ถ้ายังไม่มี (ใช้ get_resource_path เพราะผู้ใช้ขอให้ pack เข้า .exe)
    templates_dir = get_resource_path(os.path.join("assets", "templates"))
    os.makedirs(templates_dir, exist_ok=True)

    app = QApplication(sys.argv)
    
    # ตั้งค่า Icon ของโปรแกรม
    icon_path = get_resource_path("icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    # ตั้งค่า High-DPI (สำคัญสำหรับจอ 4K)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    logger.info("NUMediaBooth พร้อมใช้งาน!")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
