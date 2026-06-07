from flask import Flask, render_template, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import os

app = Flask(__name__)

# ==============================================
# 🔐 إعداد الاتصال بـ Google Sheets
# ==============================================

scope = ["https://spreadsheets.google.com/feeds", 
         "https://www.googleapis.com/auth/drive"]

# قراءة بيانات الاعتماد من متغير البيئة (للأمان) أو من ملف
if os.getenv('GOOGLE_CREDENTIALS_JSON'):
    # في منصة Render (استخدام متغير البيئة)
    try:
        creds_dict = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        print("✅ تم الاتصال باستخدام متغير البيئة")
    except Exception as e:
        print(f"❌ خطأ في قراءة متغير البيئة: {e}")
        raise
else:
    # على الجهاز المحلي (للتجربة)
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        print("✅ تم الاتصال باستخدام ملف credentials.json")
    except Exception as e:
        print(f"❌ خطأ في قراءة ملف credentials.json: {e}")
        print("💡 تأكد من وجود الملف في نفس المجلد")
        raise

# الاتصال بـ Google Sheets
try:
    client = gspread.authorize(creds)
    print("✅ تم الاتصال بـ Google Sheets بنجاح")
except Exception as e:
    print(f"❌ خطأ في الاتصال بـ Google Sheets: {e}")
    raise

# ==============================================
# 📊 فتح الشيتات (تأكد من وجودها بهذه الأسماء)
# ==============================================

try:
    products_sheet = client.open("Bakala_Products").sheet1
    print("✅ تم العثور على شيت المنتجات")
except Exception as e:
    print(f"❌ خطأ: لم يتم العثور على شيت 'Bakala_Products'")
    print("💡 تأكد من إنشاء الشيت بهذا الاسم بالضبط ومشاركته مع بريد الخدمة")
    products_sheet = None

try:
    invoices_sheet = client.open("Invoices").sheet1
    print("✅ تم العثور على شيت الفواتير")
except Exception as e:
    print(f"❌ خطأ: لم يتم العثور على شيت 'Invoices'")
    print("💡 تأكد من إنشاء الشيت بهذا الاسم بالضبط ومشاركته مع بريد الخدمة")
    invoices_sheet = None

# ==============================================
# 🔍 دوال البحث والمنتجات
# ==============================================

def get_product_by_barcode(barcode):
    """البحث عن منتج باستخدام الباركود"""
    if products_sheet is None:
        return None
    
    try:
        records = products_sheet.get_all_records()
        for row in records:
            if str(row['barcode']) == str(barcode):
                return {
                    "name": row['name'], 
                    "price": float(row['price'])
                }
        return None
    except Exception as e:
        print(f"❌ خطأ في البحث عن المنتج: {e}")
        return None

def save_invoice_to_sheet(invoice_data):
    """حفظ الفاتورة في Google Sheets"""
    if invoices_sheet is None:
        print("⚠️ لا يمكن حفظ الفاتورة: شيت الفواتير غير متاح")
        return False
    
    try:
        row = [
            invoice_data['timestamp'],
            invoice_data['total_items'],
            invoice_data['total_price'],
            invoice_data['discount'],
            invoice_data['final_price'],
            invoice_data['products_list']
        ]
        invoices_sheet.append_row(row)
        print(f"✅ تم حفظ الفاتورة بنجاح في الساعة {invoice_data['timestamp']}")
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ الفاتورة: {e}")
        return False

# ==============================================
# 🌐 مسارات (Routes) التطبيق
# ==============================================

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return render_template('index.html')

@app.route('/get_product', methods=['POST'])
def get_product():
    """الحصول على معلومات المنتج عبر الباركود"""
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
        print(f"❌ خطأ في معالجة الطلب: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/save_invoice', methods=['POST'])
def save_invoice():
    """حفظ الفاتورة النهائية"""
    try:
        data = request.get_json()
        
        # التحقق من البيانات المطلوبة
        required_fields = ['timestamp', 'total_items', 'total_price', 
                          'discount', 'final_price', 'products_list']
        
        for field in required_fields:
            if field not in data:
                return jsonify({"status": "error", "message": f"الحقل {field} مطلوب"})
        
        # حفظ الفاتورة
        success = save_invoice_to_sheet(data)
        
        if success:
            return jsonify({"status": "success", "message": "تم حفظ الفاتورة بنجاح"})
        else:
            return jsonify({"status": "error", "message": "فشل في حفظ الفاتورة"})
            
    except Exception as e:
        print(f"❌ خطأ في حفظ الفاتورة: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/health', methods=['GET'])
def health_check():
    """فحص صحة التطبيق (لـ Render)"""
    status = {
        "status": "healthy",
        "sheets_connected": products_sheet is not None and invoices_sheet is not None,
        "timestamp": datetime.now().isoformat()
    }
    return jsonify(status)

# ==============================================
# 🚀 تشغيل التطبيق
# ==============================================

if __name__ == '__main__':
    # للحصول على رقم المنفذ من Render أو استخدام 5000 محلياً
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)