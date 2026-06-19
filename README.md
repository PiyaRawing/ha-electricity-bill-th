# **Thai Electricity Bill (Home Assistant)**

Custom Integration สำหรับคำนวณค่าไฟฟ้าของประเทศไทยใน Home Assistant รองรับทั้ง **การไฟฟ้านครหลวง (MEA)** และ **การไฟฟ้าส่วนภูมิภาค (PEA)** โดยจะคำนวณค่าไฟแบบเรียลไทม์จากหน่วยมิเตอร์ (kWh) รองรับผู้ใช้ทั่วไป, ผู้ใช้ระบบ TOU (Time of Use) และผู้ใช้ที่มีระบบโซลาร์เซลล์ (ขายไฟคืน)

## **⚠️ คำเตือนที่สำคัญมาก (CRITICAL WARNING)**

Integration นี้ใช้วิธีการคำนวณโดย **"ดึงประวัติค่ามิเตอร์ย้อนหลัง"** จากฐานข้อมูลของ Home Assistant เพื่อหาค่าวันเริ่มต้นของรอบบิล

ดังนั้น ระบบจะทำงานได้ถูกต้องก็ต่อเมื่อ Home Assistant มีการเก็บประวัติ (History) ไว้นานเพียงพอ **จำเป็นต้องตั้งค่า recorder ในไฟล์ configuration.yaml ให้เก็บประวัติไว้อย่างน้อย 35 วัน** (เพื่อให้ครอบคลุม 1 รอบบิลเสมอ)

เพิ่มโค้ดด้านล่างนี้ลงในไฟล์ configuration.yaml:
```
recorder:    
  purge\_keep\_days: 35
```
*(หมายเหตุ: การเพิ่มวันเก็บประวัติอาจทำให้ขนาดฐานข้อมูลของ Home Assistant ใหญ่ขึ้น ควรตรวจสอบพื้นที่ว่างของฮาร์ดดิสก์)*

## **✨ ความสามารถหลัก (Features)**

* 🏢 **รองรับ MEA และ PEA:** ครอบคลุมผู้ให้บริการไฟฟ้าหลักของประเทศไทย  
* 📊 **คำนวณแบบขั้นบันได (Step Tariff):**  
  * กลุ่มบ้านที่ใช้ไฟไม่เกิน 150 หน่วย/เดือน (เรท 1.1 / 1.1.1)  
  * กลุ่มบ้านที่ใช้ไฟเกิน 150 หน่วย/เดือน (เรท 1.2 / 1.1.2)  
* ⏱️ **รองรับระบบ TOU อัตโนมัติ:** (เรท 1.3.2 / 1.2.2) คำนวณแยกหน่วย On-Peak และ Off-Peak ให้เองจากประวัติการใช้ไฟ โดยไม่ต้องสร้าง Utility Meter แยกให้ยุ่งยาก  
  * ⚠️ *หมายเหตุ: การคำนวณวันหยุด (Off-Peak ตลอดวัน) จะนับเฉพาะ **วันเสาร์-อาทิตย์** เท่านั้น ระบบจะยังไม่รองรับการคำนวณวันหยุดพิเศษหรือวันหยุดนักขัตฤกษ์*  
* ☀️ **รองรับ Net Billing (โซลาร์เซลล์):** สามารถใส่ Sensor ขายไฟ เพื่อนำมาหักลบเป็นรายได้ และสรุปยอดสุทธิ (Net Bill) ให้ทันที  
* ⚙️ **Re-Configure ได้ตลอดเวลา:** สามารถกดแก้ไขค่า Ft, วันที่ตัดรอบบิล หรือประเภทผู้ใช้ไฟฟ้าได้จากหน้า UI โดยไม่ต้องลบสร้างใหม่

## **📦 การติดตั้ง (Installation)**

### **วิธีที่ 1: ติดตั้งผ่าน HACS (แนะนำ)**

1. เปิด Home Assistant ไปที่ **HACS** \> **Integrations**  
2. กดปุ่มจุด 3 จุดที่มุมขวาบน เลือก **Custom repositories**  
3. ใส่ URL `https://github.com/PiyaRawing/ha-electricity-bill-th` และเลือก Category เป็น **Integration**  
4. กด Add จากนั้นค้นหาคำว่า `Thai Electricity Bill` แล้วกด Download  
5. **Restart Home Assistant** 1 รอบ

### **วิธีที่ 2: ติดตั้งแบบ Manual**

1. ดาวน์โหลดไฟล์ทั้งหมด นำโฟลเดอร์ electricity\_bill\_th ไปวางไว้ในโฟลเดอร์ custom\_components ของ Home Assistant  
2. **Restart Home Assistant** 1 รอบ

## **🛠️ วิธีการตั้งค่า (Configuration)**

1. ไปที่เมนู **Settings** \> **Devices & Services**  
2. กดปุ่ม **\+ Add Integration** ที่มุมขวาล่าง  
3. ค้นหาคำว่า **Thai Electricity Bill**  
4. ทำตามขั้นตอนบนหน้าจอ:  
   * เลือกการไฟฟ้า (MEA / PEA)  
   * เลือกประเภทผู้ใช้ไฟฟ้า (Tariff Type)  
   * กำหนดวันที่ตัดรอบบิล (Billing Date)  
   * ระบุค่า Ft ปัจจุบัน  
   * เลือก Sensor มิเตอร์ที่ใช้วัดหน่วยไฟเข้า (Imported Energy \- หน่วยเป็น kWh และห้ามรีเซ็ต)  
   * (ตัวเลือก) เลือก Sensor มิเตอร์ขายไฟ (Exported Energy \- ถ้ามี)

## **📈 Entity ที่ระบบสร้างให้**

เมื่อตั้งค่าเสร็จสิ้น ระบบจะสร้าง Sensor อย่างละเอียดให้นำไปแสดงผลบน Dashboard ดังนี้:

**หมวดหมู่ยอดรวมและหน่วยไฟฟ้า (Main Overview):**

* sensor.\[name\]\_net\_bill : ยอดรวมค่าไฟสุทธิที่ต้องจ่าย (Net Bill) (บาท)  
* sensor.\[name\]\_import\_cost : รวมค่าไฟเดือนปัจจุบัน (รวมค่าบริการ/Ft/Vat) (บาท)  
* sensor.\[name\]\_import\_units : จำนวนหน่วยไฟที่ใช้ไปในรอบบิลนี้ (kWh)

**หมวดหมู่รายละเอียดค่าใช้จ่าย (Bill Breakdown):**

* sensor.\[name\]\_base\_cost : ค่าพลังงานไฟฟ้า (บาท)  
* sensor.\[name\]\_service\_charge : ค่าบริการรายเดือน (บาท)  
* sensor.\[name\]\_ft\_cost : ค่าไฟฟ้าผันแปร (Ft) (บาท)  
* sensor.\[name\]\_total\_before\_vat : รวมค่าไฟฟ้าก่อนภาษีมูลค่าเพิ่ม (บาท)  
* sensor.\[name\]\_vat : ภาษีมูลค่าเพิ่ม 7% (บาท)

**หมวดหมู่มิเตอร์ตั้งต้น (Meter Readings):**

* sensor.\[name\]\_current\_import\_meter : เลขอ่านมิเตอร์ครั้งหลัง (ดึงจากสถานะปัจจุบัน)  
* sensor.\[name\]\_previous\_import\_meter : เลขอ่านมิเตอร์ครั้งก่อน (ค่าเริ่มต้นรอบบิล)

**พิเศษ: สำหรับผู้ใช้ระบบ โซลาร์เซลล์ (Net Billing)**

* sensor.\[name\]\_export\_units : จำนวนหน่วยไฟที่ขายไปในรอบบิลนี้ (kWh)  
* sensor.\[name\]\_export\_income\_before\_tax : รายได้จากการขายไฟก่อนหักภาษี (บาท)  
* sensor.\[name\]\_export\_tax : หักภาษี 1% สำหรับการขายไฟคืน (บาท)  
* sensor.\[name\]\_export\_income : รายได้จากการขายไฟคืนสุทธิ (บาท)  
* sensor.\[name\]\_current\_export\_meter : เลขอ่านมิเตอร์ขายไฟครั้งหลัง  
* sensor.\[name\]\_previous\_export\_meter : เลขอ่านมิเตอร์ขายไฟครั้งก่อน

**พิเศษ: สำหรับผู้ใช้ระบบ TOU**

* sensor.\[name\]\_on\_peak\_units : จำนวนหน่วยที่ใช้ในช่วง On-Peak  
* sensor.\[name\]\_off\_peak\_units : จำนวนหน่วยที่ใช้ในช่วง Off-Peak  
* sensor.\[name\]\_on\_peak\_cost : ค่าพลังงานไฟฟ้า On-Peak (บาท)  
* sensor.\[name\]\_off\_peak\_cost : ค่าพลังงานไฟฟ้า Off-Peak (บาท)

<img width="1111" height="582" alt="image" src="https://github.com/user-attachments/assets/2ddbab21-f594-4845-b10a-2b26ce374b3c" />
<img width="368" height="837" alt="image" src="https://github.com/user-attachments/assets/481b6a2e-5c68-43eb-a679-610b31c4a870" />


## **📚 ข้อมูลอ้างอิงอัตราค่าไฟฟ้า (Tariff References)**

ระบบคำนวณโดยอิงจากโครงสร้างอัตราค่าไฟฟ้าอย่างเป็นทางการ ดังนี้:

* **การไฟฟ้านครหลวง (MEA):** [โครงสร้างอัตราค่าไฟฟ้า MEA](https://www.mea.or.th/our-services/service-rates/other/D5xEaEwgU)  
* **การไฟฟ้าส่วนภูมิภาค (PEA):** [โครงสร้างอัตราค่าไฟฟ้า PEA (PDF)](https://www.pea.co.th/sites/default/files/documents/tariff/Electricity_Tariff_MAY_2023.pdf)
* **อัพเดทเดือนมิถุนายน 2569**
