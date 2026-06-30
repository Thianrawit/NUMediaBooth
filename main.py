"""
NUMediaBooth — Photobooth Application
=======================================
Entry point ของโปรแกรม
"""

import sys
import os
import logging
import time

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap

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

    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    
    # ตั้งค่า Icon ของโปรแกรม
    icon_path = get_resource_path("icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    # ตั้งค่า High-DPI (สำคัญสำหรับจอ 4K)
    app.setStyle("Fusion")

    # --- เริ่มทำ Splash Screen ---
    splash_image_path = get_resource_path(os.path.join("image", "splash_logo.png"))
    splash_pixmap = QPixmap(splash_image_path)

    # 2. คำนวณ Responsive แบบป้องกันภาพแตก!
    screen_geometry = app.primaryScreen().geometry()
    target_width = int(screen_geometry.width() * 0.5)

    # 🔥 พระเอกอยู่ตรงนี้: สั่งห้ามถ่างรูปเกินขนาดต้นฉบับ (1247px)
    if target_width > splash_pixmap.width():
        target_width = splash_pixmap.width()

    # ทำ Smooth Scale
    splash_pixmap = splash_pixmap.scaledToWidth(
        target_width, 
        Qt.TransformationMode.SmoothTransformation
    )

    # 3. รองรับพื้นหลังโปร่งใส
    splash = QSplashScreen(splash_pixmap, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    splash.show()

    # 4. บังคับโหลด UI ทันที
    app.processEvents()

    # หน่วงเวลาโหลด (ของจริงอย่าลืมเอาไปครอบตอนโหลด Model หรือต่อเน็ตนะ)
    time.sleep(2) 
    # --- จบส่วน Splash Screen ---

    window = MainWindow()
    window.show()

    # ปิด Splash Screen 
    splash.finish(window)

    logger.info("NUMediaBooth พร้อมใช้งาน!")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
