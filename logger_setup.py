import os
import sys
import logging
import shutil
from datetime import datetime
from path_manager import get_dynamic_path

def setup_logger():
    """
    ตั้งค่าระบบ Logging สำหรับทั้งแอปพลิเคชัน
    - บันทึก Log ลงในโฟลเดอร์ logs/app.log
    - สร้างโฟลเดอร์ logs/crash_dumps เตรียมไว้
    """
    logs_dir = get_dynamic_path("logs")
    crash_dir = os.path.join(logs_dir, "crash_dumps")
    
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(crash_dir, exist_ok=True)
    
    log_file_path = os.path.join(logs_dir, "app.log")
    error_log_file_path = os.path.join(logs_dir, "appError.log")
    
    log_format = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    
    # Configure root logger
    # ต้อง clear handlers เก่าออกก่อน เพราะใน main.py อาจจะเคยมีการตั้งค่าไว้
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    error_handler = logging.FileHandler(error_log_file_path, mode='a', encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
        
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file_path, mode='w', encoding='utf-8'),
            error_handler
        ]
    )
    
    logging.info("==================================================")
    logging.info("NUMediaBooth Logger Initialized")
    logging.info(f"Log file saved to: {log_file_path}")
    logging.info("==================================================")
    
    return crash_dir

def save_crash_dump(image_path: str, context: str) -> str:
    """
    บันทึกภาพล่าสุดที่ทำให้เกิดข้อผิดพลาดร้ายแรงลงในโฟลเดอร์ crash_dumps
    
    Args:
        image_path: ตำแหน่งภาพต้นฉบับ
        context: บริบทที่เกิด error (เช่น 'print_failed', 'upload_failed')
    """
    try:
        if not os.path.exists(image_path):
            return ""
            
        crash_dir = get_dynamic_path(os.path.join("logs", "crash_dumps"))
        os.makedirs(crash_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = os.path.splitext(image_path)[1]
        crash_filename = f"{context}_{timestamp}{file_ext}"
        crash_filepath = os.path.join(crash_dir, crash_filename)
        
        shutil.copy2(image_path, crash_filepath)
        logging.getLogger(__name__).info(f"บันทึกไฟล์ Crash Dump สำเร็จที่: {crash_filepath}")
        return crash_filepath
    except Exception as e:
        logging.getLogger(__name__).error(f"ไม่สามารถบันทึกไฟล์ Crash Dump ได้: {e}")
        return ""
