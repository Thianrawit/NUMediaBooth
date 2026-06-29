import os
import sys

def get_resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    ใช้สำหรับไฟล์ที่ฝังไปกับ .exe เช่น รูปภาพ UI, icon, default assets
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)

def get_dynamic_path(relative_path: str) -> str:
    """
    Get absolute path to dynamic files, ensuring they are stored relative to the executable.
    ใช้สำหรับไฟล์ที่มีการเปลี่ยนแปลง เช่น logs, ไฟล์ save, รูปถ่ายชั่วคราว
    """
    if getattr(sys, 'frozen', False):
        # The application is frozen, get directory of executable
        base_path = os.path.dirname(sys.executable)
    else:
        # The application is not frozen
        base_path = os.path.dirname(os.path.abspath(__file__))
        
    return os.path.join(base_path, relative_path)
