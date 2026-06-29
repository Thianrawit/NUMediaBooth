import logging
try:
    import win32print
except ImportError:
    win32print = None

from PyQt6.QtCore import Qt, QSizeF, QMarginsF, QRectF
from PyQt6.QtGui import QImage, QPainter, QPageSize, QPageLayout
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo

from logger_setup import save_crash_dump

logger = logging.getLogger(__name__)

def _try_set_media_type(printer_name: str, media_type_str: str):
    """
    พยายามใช้ win32print เพื่อตั้งค่า DEVMODE.MediaType ของปริ้นเตอร์
    (อาจจะไม่ได้ผลกับ Printer บางรุ่นที่ใช้ Driver เฉพาะทาง)
    """
    if not win32print:
        return
        
    media_map = {
        "กระดาษธรรมดา": 1,
        "Matte Photo Paper": 2, 
        "กระดาษเคลือบมันภาพถ่าย": 3,
        "กระดาษภาพถ่ายเคลือบมันพิเศษ II": 3,
        "Photo Paper Pro Luster": 3,
        "กระดาษการ์ด": 1
    }
    target_media_id = media_map.get(media_type_str, 1)
    
    try:
        # เปิด Printer ขอสิทธิ์ระดับ PRINTER_ALL_ACCESS (ต้องเป็น Admin หรือเจ้าของเครื่อง)
        PRINTER_ALL_ACCESS = 0x000F000C
        pHandle = win32print.OpenPrinter(printer_name, {"DesiredAccess": PRINTER_ALL_ACCESS})
        try:
            properties = win32print.GetPrinter(pHandle, 2)
            devmode = properties["pDevMode"]
            if hasattr(devmode, 'MediaType'):
                devmode.MediaType = target_media_id
                properties["pDevMode"] = devmode
                win32print.SetPrinter(pHandle, 2, properties, 0)
                logger.info(f"พยายามอัปเดต MediaType เป็น {media_type_str} ({target_media_id}) ผ่าน DEVMODE สำเร็จ")
        finally:
            win32print.ClosePrinter(pHandle)
    except Exception as e:
        logger.debug(f"ไม่สามารถเปลี่ยน MediaType ผ่าน API ได้โดยตรง (อาจติดเรื่องสิทธิ์หรือ Driver ห้าม): {e}")

def silent_print_photo(image_path: str, config_data: dict) -> bool:
    """
    ฟังก์ชันสำหรับการสั่งพิมพ์ออกแบบอัตโนมัติ (Silent Print) โดยไม่มีหน้าต่างยืนยัน
    
    Args:
        image_path: Path ของรูปภาพที่จะปริ้น
        config_data: Dictionary การตั้งค่า (ควรมี printer_name, paper_size, print_copies)
        
    Returns:
        bool: True ถ้าส่งคำสั่งสำเร็จ, False ถ้าเกิดข้อผิดพลาด
    """
    printer_name = config_data.get("printer_name", "")
    
    if not printer_name or printer_name.startswith("—"):
        logger.warning("ไม่มีการตั้งค่าเครื่องปริ้นเตอร์ ข้ามการพิมพ์")
        return False
        
    printer_info = QPrinterInfo.printerInfo(printer_name)
    if printer_info.isNull():
        logger.error(f"ไม่พบข้อมูลของเครื่องปริ้นเตอร์: {printer_name}")
        return False
        
    # พยายามเปลี่ยนชนิดกระดาษผ่าน win32print ก่อนที่ Qt จะดึงค่าไปใช้
    media_type_str = config_data.get("media_type", "กระดาษธรรมดา")
    _try_set_media_type(printer_name, media_type_str)

    # 1. สร้าง QPrinter พร้อมตั้งค่าชื่อเครื่องปริ้นเตอร์ (ใช้โหมด HighResolution เพื่อความคมชัด)
    printer = QPrinter(printer_info, QPrinter.PrinterMode.HighResolution)
    
    # 2. ตั้งค่าขนาดกระดาษ (Paper Size)
    paper_size_str = config_data.get("paper_size", "A4")
    if "A4" in paper_size_str:
        page_size = QPageSize(QPageSize.PageSizeId.A4)
    elif "A5" in paper_size_str:
        page_size = QPageSize(QPageSize.PageSizeId.A5)
    elif "A6" in paper_size_str:
        page_size = QPageSize(QPageSize.PageSizeId.A6)
    elif "2x6" in paper_size_str:
        page_size = QPageSize(QSizeF(2, 6), QPageSize.Unit.Inch)
    elif "4x6" in paper_size_str:
        page_size = QPageSize(QSizeF(4, 6), QPageSize.Unit.Inch)
    elif "5x7" in paper_size_str:
        page_size = QPageSize(QSizeF(5, 7), QPageSize.Unit.Inch)
    else:
        page_size = QPageSize(QPageSize.PageSizeId.A4)
        
    printer.setPageSize(page_size)
    
    # บังคับเป็นแนวตั้งเสมอ
    printer.setPageOrientation(QPageLayout.Orientation.Portrait)
    
    # 3. ตั้งค่าจำนวนแผ่น (Copies)
    copies = int(config_data.get("print_copies", 1))
    printer.setCopyCount(copies)
    
    # 4. ตั้งค่า Margin ของกระดาษเป็น 0 (ไร้ขอบ)
    layout = printer.pageLayout()
    layout.setMargins(QMarginsF(0, 0, 0, 0))
    # บังคับอัปเดต Layout กลับไปที่ Printer
    printer.setPageLayout(layout)
    
    # 5. โหลดรูปภาพเป็น QImage
    image = QImage(image_path)
    if image.isNull():
        logger.error(f"ไม่สามารถโหลดรูปภาพได้: {image_path}")
        return False
        
    # 6. ใช้ QPainter วาด QImage ลงบนกระดาษ (Silent Print)
    painter = QPainter()
    try:
        # เริ่มการพิมพ์ (จะส่งข้อมูลเข้า Spooler อัตโนมัติ)
        if not painter.begin(printer):
            logger.error("ไม่สามารถเริ่มคำสั่งพิมพ์ลง QPrinter ได้")
            save_crash_dump(image_path, "printer_begin_failed")
            return False
            
        # ดึงขนาดของกระดาษบนอุปกรณ์พิมพ์ (หน่วยเป็นพิกเซล)
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
        
        page_w = page_rect.width()
        page_h = page_rect.height()
        
        if page_w <= 0 or page_h <= 0:
            logger.error("ขนาดกระดาษบน Printer เป็น 0 ยุติการพิมพ์")
            save_crash_dump(image_path, "printer_zero_page_size")
            painter.end()
            return False
            
        img_w = image.width()
        img_h = image.height()
        
        # คำนวณ Aspect Ratio เพื่อ Scale รูปภาพให้พอดีกับกระดาษแบบเต็มแผ่น (Fit)
        ratio = min(page_w / img_w, page_h / img_h)
        
        target_w = img_w * ratio
        target_h = img_h * ratio
        
        # จัดกึ่งกลางภาพลงบนกระดาษ
        x_offset = (page_w - target_w) / 2.0
        y_offset = (page_h - target_h) / 2.0
        
        target_rect = QRectF(x_offset, y_offset, target_w, target_h)
        source_rect = QRectF(0, 0, img_w, img_h)
        
        # ปล่อยให้ QPainter ของ Printer จัดการ Scale ภาพให้เอง จะแม่นยำและไม่เสีย Memory ฟรีๆ
        painter.drawImage(target_rect, image, source_rect)
        
        painter.end()
        logger.info(f"สั่งพิมพ์ภาพ {image_path} ไปยัง {printer_name} สำเร็จ")
        return True
        
    except Exception as e:
        logger.error(f"เกิดข้อผิดพลาดขณะพิมพ์: {e}")
        save_crash_dump(image_path, "print_failed_exception")
        if painter.isActive():
            painter.end()
        return False
