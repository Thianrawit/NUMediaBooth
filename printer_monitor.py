import logging

try:
    import win32print
except ImportError:
    win32print = None

from PyQt6.QtPrintSupport import QPrinterInfo, QPrinter

logger = logging.getLogger(__name__)

def check_printer_status(printer_name: str) -> tuple[bool, str]:
    """
    ตรวจสอบสถานะของเครื่องปริ้นเตอร์ว่ามีความผิดปกติหรือไม่ 
    (เช่น Paper Jam, Out of Paper, Low Ink)
    
    Returns:
        (is_ok: bool, error_msg: str)
    """
    if not printer_name or printer_name.startswith("—"):
        return False, "ไม่ได้ตั้งค่าชื่อเครื่องปริ้นเตอร์ไว้"
        
    printer_info = QPrinterInfo.printerInfo(printer_name)
    if printer_info.isNull():
        return False, f"ไม่พบเครื่องปริ้นเตอร์ชื่อ: {printer_name} ในระบบ"
        
    errors = []
    
    # 1. เช็คด้วย win32print เพื่อดึงรายละเอียดเชิงลึกแบบ Windows
    if win32print:
        try:
            # ใช้ PRINTER_ACCESS_USE เพื่ออ่านสถานะเฉยๆ
            pHandle = win32print.OpenPrinter(printer_name)
            info = win32print.GetPrinter(pHandle, 2)
            status = info.get("Status", 0)
            win32print.ClosePrinter(pHandle)
            
            if status & win32print.PRINTER_STATUS_PAPER_JAM:
                errors.append("กระดาษติด (Paper Jam)")
            if status & win32print.PRINTER_STATUS_PAPER_OUT:
                errors.append("กระดาษหมด (Out of Paper)")
            if status & win32print.PRINTER_STATUS_NO_TONER or status & win32print.PRINTER_STATUS_TONER_LOW:
                errors.append("หมึกหมดหรือเหลือน้อย (Low/No Ink)")
            if status & win32print.PRINTER_STATUS_DOOR_OPEN:
                errors.append("ฝาเครื่องเปิดอยู่ (Door Open)")
            if status & win32print.PRINTER_STATUS_OFFLINE:
                errors.append("เครื่องปริ้น Offline")
            if status & win32print.PRINTER_STATUS_ERROR:
                # ถ้ามันแจ้ง Error รวมๆ เราจะบอกแค่ Error เว้นแต่จะมีอย่างอื่นบอกด้วย
                if not errors:
                    errors.append("เครื่องปริ้นแจ้ง Error (โปรดตรวจสอบที่ตัวเครื่อง)")
                    
        except Exception as e:
            logger.debug(f"ไม่สามารถตรวจสอบสถานะด้วย win32print ได้: {e}")
            
    # 2. ถ้าระบบ Windows API อ่านไม่เจอ (หรือไม่มี) ใช้ QPrinterInfo สำรอง
    if not errors:
        state = printer_info.state()
        if state == QPrinter.PrinterState.Error:
            errors.append("เกิดข้อผิดพลาดที่เครื่องปริ้น (QPrinter Error)")
        elif state == QPrinter.PrinterState.Aborted:
            errors.append("งานถูกยกเลิก (Aborted)")

    if errors:
        error_msg = ", ".join(errors)
        logger.warning(f"ตรวจสอบพบสถานะปริ้นเตอร์ผิดปกติ: {error_msg}")
        return False, error_msg
        
    return True, ""
