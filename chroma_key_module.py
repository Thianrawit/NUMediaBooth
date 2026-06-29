import numpy as np
from scipy import ndimage
from PIL import Image
import logging

logger = logging.getLogger(__name__)

def remove_color_background(image: Image.Image, target_rgb: tuple[int, int, int], tolerance: int, edge_crop: int) -> Image.Image:
    """
    ลบพื้นหลังตามสีที่ระบุ โดยใช้ Tolerance (ความคลาดเคลื่อนสี) และ Edge Crop (กัดขอบ)
    
    Args:
        image: รูปภาพต้นฉบับ (PIL.Image) โหมด RGBA หรือ RGB
        target_rgb: สีที่ต้องการลบ (R, G, B)
        tolerance: ค่าความคลาดเคลื่อนที่ยอมรับได้ (0-255)
        edge_crop: จำนวนพิกเซลที่ต้องการกัดขอบ (erosion) เพื่อลดขอบสีเขียวที่ติดมา
        
    Returns:
        รูปภาพที่ตัดพื้นหลังให้โปร่งใสแล้ว (PIL.Image โหมด RGBA)
    """
    # ทำให้มั่นใจว่าเป็น RGBA
    if image.mode != "RGBA":
        image = image.convert("RGBA")
        
    # แปลงเป็น Numpy Array
    img_array = np.array(image)
    
    # ดึงเฉพาะช่องสี R, G, B (ไม่เอา Alpha มาคำนวณระยะห่างสี)
    r, g, b, a = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2], img_array[:,:,3]
    
    tr, tg, tb = target_rgb
    
    # คำนวณความแตกต่างของสีแบบง่าย (หรือจะใช้ Euclidean distance ก็ได้)
    # ใช้ Euclidean distance ค่อนข้างแม่นยำกว่า
    color_diff = np.sqrt(
        (r.astype(np.float32) - tr)**2 +
        (g.astype(np.float32) - tg)**2 +
        (b.astype(np.float32) - tb)**2
    )
    
    # สร้าง Mask ของส่วนที่ "ต้องถูกลบ" (สีใกล้เคียงกับ target_rgb ภายใน tolerance)
    # ถ้าค่า diff <= tolerance ถือว่าเป็นพื้นหลังที่จะลบ
    # แปลว่า mask_to_remove เป็น True ตรงที่เป็นพื้นหลัง
    mask_to_remove = color_diff <= tolerance
    
    # ถ้ามีการกัดขอบ (Edge Crop/Erosion) ให้ขยายขนาดของ Mask พื้นหลังเข้าไปในตัวภาพ
    if edge_crop > 0:
        # ใช้ binary_dilation ขยายพื้นที่ mask_to_remove เข้าไปกินตัวภาพจริง
        # กัด 1 px = iterations 1
        mask_to_remove = ndimage.binary_dilation(mask_to_remove, iterations=edge_crop)
        
    # อัปเดตช่อง Alpha (A) ให้เป็น 0 (โปร่งใส) ตรงที่ mask_to_remove เป็น True
    img_array[mask_to_remove, 3] = 0
    
    # คืนค่ากลับเป็น PIL.Image
    return Image.fromarray(img_array, mode="RGBA")
