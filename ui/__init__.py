"""
UI Package สำหรับ NUMediaBooth Photobooth Application
=====================================================
ประกอบไปด้วย Widgets หลัก 3 หน้า + MainWindow
"""

from ui.main_window import MainWindow
from ui.home_widget import HomeWidget
from ui.template_select_widget import TemplateSelectWidget
from ui.setting_widget import SettingWidget
from ui.capture_widget import CameraCaptureWidget
from ui.finish_widget import FinishWidget

__all__ = [
    "MainWindow",
    "HomeWidget",
    "TemplateSelectWidget",
    "SettingWidget",
    "CameraCaptureWidget",
]
