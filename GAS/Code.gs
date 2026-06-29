function doPost(e) {
  try {
    // อ่านค่า Payload ที่ส่งมาจาก Python
    var data = JSON.parse(e.postData.contents);
    var base64Data = data.image;
    var folderId = data.folder_id;
    var fileName = data.filename || "photobooth_capture.jpg";
    
    // แปลงข้อมูล Base64 กลับเป็น Blob (ไฟล์)
    var byteCharacters = Utilities.base64Decode(base64Data);
    var blob = Utilities.newBlob(byteCharacters, 'image/jpeg', fileName);
    
    // เข้าถึงโฟลเดอร์ใน Google Drive ตาม ID
    var folder = DriveApp.getFolderById(folderId);
    
    // สร้างไฟล์ลงในโฟลเดอร์นั้น
    var file = folder.createFile(blob);
    
    // ตั้งค่า Permission ถ้าต้องการให้แชร์ได้ทันที (Optional)
    // file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    
    // ส่งผลลัพธ์กลับไปยัง Python
    return ContentService.createTextOutput(JSON.stringify({
      "status": "success",
      "url": file.getUrl(),
      "id": file.getId()
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (error) {
    // กรณีเกิด Error
    return ContentService.createTextOutput(JSON.stringify({
      "status": "error",
      "message": error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
