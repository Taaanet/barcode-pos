from flask import Flask, render_template, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import os

app = Flask(__name__)

print("=" * 50)
print("🚀 بدء تشغيل التطبيق...")
print("=" * 50)

# ==============================================
# إعداد الاتصال بـ Google Sheets
# ==============================================

scope = ["https://spreadsheets.google.com/feeds", 
         "https://www.googleapis.com/auth/drive"]

# محاولة الاتصال بطرق مختلفة
client = None
products_sheet = None
invoices_sheet = None

# الطريقة 1: من متغير البيئة (لـ Render)
creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
if creds_json:
    try:
        print("📌 محاولة الاتصال باستخدام متغير البيئة...")
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        print("✅ تم الاتصال بنجاح باستخدام متغير البيئة")
    except Exception as e:
        print(f"❌ فشل الاتصال بمتغير البيئة: {e}")

# الطريقة 2: من ملف credentials.json (للتجربة المحلية)
if not client and os.path.exists("credentials.json"):
    try:
        print("📌 محاولة الاتصال باستخدام ملف credentials.json...")
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        print("✅ تم الاتصال بنجاح باستخدام ملف credentials.json")
    except Exception as e:
        print(f"❌ فشل الاتصال بالملف: {e}")

if not client:
    print("❌ فشل الاتصال بـ Google Sheets بجميع الطرق")
else:
    # فتح شيت المنتجات
    try:
        products_sheet = client.open("Bakala_Products").sheet1
        print("✅ تم العثور على شيت 'Bakala_Products'")
        
        # عرض عدد المنتجات
        records = products_sheet.get_all_records()
        print(f"📊 عدد المنتجات: {len(records)}")
        
        # عرض عينة
        if len(records) > 0:
            print("📋 عينة من المنتجات:")
            for i, row in enumerate(records[:3]):
                print(f"   {i+1}. {row.get('barcode')} - {row.get('name')} - {row.get('price')}")
    except Exception as e:
        print(f"❌ خطأ في فتح شيت المنتجات: {e}")
        print("💡 تأكد من مشاركة الشيت مع البريد: barcode-pos-service@barcodepos.iam.gserviceaccount.com")
    
    # فتح شيت الفواتير
    try:
        invoices_sheet = client.open("Invoices").sheet1
        print("✅ تم العثور على شيت 'Invoices'")
    except Exception as e:
        print(f"⚠️ شيت الفواتير غير موجود: {e}")
        print("💡 سيتم إنشاؤه عند أول فاتورة")

print("=" * 50)

# ==============================================
# الدوال الأساسية
# ==============================================

def get_product_by_barcode(barcode):
    """البحث عن منتج باستخدام الباركود"""
    if products_sheet is None:
        return None
    
    try:
        records = products_sheet.get_all_records()
        for row in records:
            row_barcode = str(row.get('barcode', ''))
            if row_barcode == str(barcode):
                return {
                    "name": row.get('name', 'غير معروف'),
                    "price": float(row.get('price', 0))
                }
        return None
    except Exception as e:
        print(f"❌ خطأ في البحث: {e}")
        return None

def save_invoice_to_sheet(invoice_data):
    """حفظ الفاتورة في Google Sheets"""
    if invoices_sheet is None:
        print("⚠️ لا يمكن حفظ الفاتورة: شيت الفواتير غير متاح")
        return False
    
    try:
        row = [
            invoice_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            invoice_data.get('total_items', 0),
            invoice_data.get('total_price', 0),
            invoice_data.get('discount', 0),
            invoice_data.get('final_price', 0),
            invoice_data.get('products_list', '')
        ]
        invoices_sheet.append_row(row)
        print("✅ تم حفظ الفاتورة بنجاح")
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ الفاتورة: {e}")
        return False

# ==============================================
# مسارات التطبيق
# ==============================================

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return render_template('index.html')

@app.route('/get_product', methods=['POST'])
def get_product():
    """الحصول على معلومات المنتج"""
    try:
        data = request.get_json()
        barcode = data.get('barcode')
        
        if not barcode:
            return jsonify({"status": "error", "message": "الباركود مطلوب"})
        
        product = get_product_by_barcode(barcode)
        
        if product:
            return jsonify({
                "status": "found",
                "name": product['name'],
                "price": product['price']
            })
        else:
            return jsonify({
                "status": "not_found",
                "message": "المنتج غير موجود في قاعدة البيانات"
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/save_invoice', methods=['POST'])
def save_invoice():
    """حفظ الفاتورة"""
    try:
        data = request.get_json()
        success = save_invoice_to_sheet(data)
        
        if success:
            return jsonify({"status": "success", "message": "تم حفظ الفاتورة"})
        else:
            return jsonify({"status": "error", "message": "فشل الحفظ"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/debug')
def debug():
    """صفحة التصحيح"""
    if products_sheet is None:
        return """
        <html>
        <body style="font-family: Arial; direction: rtl; padding: 20px;">
            <h1 style="color: red;">❌ شيت المنتجات غير متصل</h1>
            <h3>الرجاء التحقق من:</h3>
            <ol>
                <li>وجود شيت باسم 'Bakala_Products' في Google Sheets</li>
                <li>مشاركة الشيت مع البريد: <strong>barcode-pos-service@barcodepos.iam.gserviceaccount.com</strong></li>
                <li>متغير البيئة GOOGLE_CREDENTIALS_JSON مضبوط بشكل صحيح في Render</li>
            </ol>
            <hr>
            <h3>البريد الإلكتروني للخدمة:</h3>
            <p><code>barcode-pos-service@barcodepos.iam.gserviceaccount.com</code></p>
            <p>يجب إضافة هذا البريد كمحرر في شيت Bakala_Products</p>
        </body>
        </html>
        """
    
    try:
        records = products_sheet.get_all_records()
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial; direction: rtl; padding: 20px; }}
                .success {{ color: green; background: #e0ffe0; padding: 15px; border-radius: 5px; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: right; }}
                th {{ background: #4CAF50; color: white; }}
            </style>
        </head>
        <body>
            <div class="success">
                <h1>✅ الاتصال ناجح!</h1>
                <p><strong>عدد المنتجات في شيت Bakala_Products:</strong> {len(records)}</p>
            </div>
            
            <h2>📋 قائمة المنتجات:</h2>
            <table>
                <tr>
                    <th>الباركود (barcode)</th>
                    <th>الاسم (name)</th>
                    <th>السعر (price)</th>
                </tr>
        """
        
        for row in records:
            html += f"""
                <tr>
                    <td>{row.get('barcode', '')}</td>
                    <td>{row.get('name', '')}</td>
                    <td>{row.get('price', '')}</td>
                </tr>
            """
        
        html += """
            </table>
            <p><a href="/">← العودة إلى التطبيق</a></p>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return f"<h1>خطأ: {e}</h1>"

@app.route('/health')
def health():
    """فحص صحة التطبيق"""
    return jsonify({
        "status": "ok",
        "sheets_connected": products_sheet is not None,
        "products_count": len(products_sheet.get_all_records()) if products_sheet else 0
    })

# ==============================================
# تشغيل التطبيق
# ==============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 التشغيل على المنفذ: {port}")
    app.run(host='0.0.0.0', port=port, debug=False)