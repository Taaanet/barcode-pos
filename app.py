from flask import Flask, render_template, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import os
import sys

app = Flask(__name__)

print("=" * 50)
print("🚀 بدء تشغيل التطبيق...")
print("=" * 50)

# ==============================================
# إعداد الاتصال بـ Google Sheets
# ==============================================

scope = ["https://spreadsheets.google.com/feeds", 
         "https://www.googleapis.com/auth/drive"]

# التحقق من وجود متغير البيئة
env_var = os.getenv('GOOGLE_CREDENTIALS_JSON')
print(f"📌 متغير GOOGLE_CREDENTIALS_JSON موجود: {'نعم' if env_var else 'لا'}")

if env_var:
    print(f"📌 طول المتغير: {len(env_var)} حرف")
    print(f"📌 أول 50 حرف: {env_var[:50]}...")
    
    try:
        creds_dict = json.loads(env_var)
        print("✅ تم تحويل JSON بنجاح")
        
        # التحقق من وجود البريد الإلكتروني
        if 'client_email' in creds_dict:
            print(f"✅ البريد الإلكتروني للخدمة: {creds_dict['client_email']}")
        else:
            print("❌ client_email غير موجود في JSON")
            
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        print("✅ تم إنشاء بيانات الاعتماد بنجاح")
        
    except json.JSONDecodeError as e:
        print(f"❌ خطأ في تحويل JSON: {e}")
        print("💡 تأكد من أن محتوى المتغير هو JSON صحيح")
        sys.exit(1)
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")
        sys.exit(1)
else:
    print("❌ متغير البيئة GOOGLE_CREDENTIALS_JSON غير موجود")
    print("💡 أضفه في Render Dashboard → Environment → Environment Variables")
    sys.exit(1)

# الاتصال بـ Google Sheets
print("\n🔗 محاولة الاتصال بـ Google Sheets...")
try:
    client = gspread.authorize(creds)
    print("✅ تم الاتصال بـ Google Sheets بنجاح")
except Exception as e:
    print(f"❌ فشل الاتصال: {e}")
    sys.exit(1)

# فتح الشيتات
print("\n📊 محاولة فتح الشيتات...")

try:
    products_sheet = client.open("Bakala_Products").sheet1
    print("✅ تم العثور على شيت 'Bakala_Products'")
    
    # اختبار قراءة أول صف
    test_record = products_sheet.row_values(1)
    print(f"📋 الصف الأول في المنتجات: {test_record}")
    
except gspread.exceptions.SpreadsheetNotFound:
    print("❌ لم يتم العثور على شيت 'Bakala_Products'")
    print("💡 تأكد من:")
    print("   1. الاسم صحيح (حساس للحروف)")
    print("   2. تمت مشاركة الشيت مع البريد:", creds_dict.get('client_email', 'غير معروف'))
    
    # محاولة عرض كل الشيتات المتاحة
    try:
        all_sheets = client.openall()
        print("\n📋 الشيتات المتاحة:")
        for sheet in all_sheets:
            print(f"   - {sheet.title}")
    except:
        pass
    
    products_sheet = None
    
except Exception as e:
    print(f"❌ خطأ آخر: {e}")
    products_sheet = None

try:
    invoices_sheet = client.open("Invoices").sheet1
    print("✅ تم العثور على شيت 'Invoices'")
except gspread.exceptions.SpreadsheetNotFound:
    print("❌ لم يتم العثور على شيت 'Invoices'")
    invoices_sheet = None
except Exception as e:
    print(f"❌ خطأ آخر: {e}")
    invoices_sheet = None

print("\n" + "=" * 50)
print("🏁 انتهى التهيئة")
print("=" * 50)

# ==============================================
# 🔍 دوال البحث والمنتجات
# ==============================================

def get_product_by_barcode(barcode):
    """البحث عن منتج باستخدام الباركود"""
    if products_sheet is None:
        return None
    
    try:
        records = products_sheet.get_all_records()
        print(f"🔍 البحث عن باركود: {barcode}")
        print(f"📊 عدد المنتجات في الشيت: {len(records)}")
        
        for row in records:
            print(f"   مقارنة مع: '{row['barcode']}'")
            if str(row['barcode']) == str(barcode):
                print(f"   ✅ تم العثور على المنتج: {row['name']}")
                return {
                    "name": row['name'], 
                    "price": float(row['price'])
                }
        print(f"   ❌ لم يتم العثور على الباركود {barcode}")
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

@app.route('/debug')
def debug():
    """مسار التصحيح: عرض جميع المنتجات من Google Sheets"""
    if products_sheet is None:
        return """
        <h1>❌ شيت المنتجات غير متصل</h1>
        <p>يرجى التحقق من:</p>
        <ul>
            <li>وجود شيت باسم 'Bakala_Products' في Google Sheets</li>
            <li>مشاركة الشيت مع البريد الإلكتروني للخدمة</li>
            <li>متغير البيئة GOOGLE_CREDENTIALS_JSON مضبوط بشكل صحيح</li>
        </ul>
        """
    
    try:
        records = products_sheet.get_all_records()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Debug: منتجات Google Sheets</title>
            <meta charset="UTF-8">
            <style>
                body { font-family: Arial; direction: rtl; padding: 20px; }
                table { border-collapse: collapse; width: 100%; margin: 20px 0; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: right; }
                th { background-color: #4CAF50; color: white; }
                .success { color: green; }
                .error { color: red; }
                .info { background-color: #e7f3ff; padding: 10px; margin: 10px 0; }
            </style>
        </head>
        <body>
            <h1>🔍 Debug: المنتجات في Google Sheets</h1>
            <div class="info">
                <p><strong>✅ شيت 'Bakala_Products' متصل بنجاح</strong></p>
                <p>📊 عدد المنتجات: <strong>{}</strong></p>
            </div>
        """.format(len(records))
        
        if len(records) > 0:
            html += "<h2>📋 قائمة المنتجات:</h2>"
            html += "<table>"
            html += "<tr><th>الباركود (barcode)</th><th>الاسم (name)</th><th>السعر (price)</th></tr>"
            
            for row in records:
                html += f"<tr>"
                html += f"<td>{row.get('barcode', '')}</td>"
                html += f"<td>{row.get('name', '')}</td>"
                html += f"<td>{row.get('price', '')}</td>"
                html += f"</tr>"
            
            html += "</table>"
            
            # اختبار البحث عن test123
            html += "<h2>🧪 اختبار البحث:</h2>"
            test_result = get_product_by_barcode('test123')
            if test_result:
                html += f"<p class='success'>✅ البحث عن 'test123': تم العثور على '{test_result['name']}' - السعر: {test_result['price']}</p>"
            else:
                html += "<p class='error'>❌ البحث عن 'test123': لم يتم العثور على المنتج</p>"
            
            # اختبار البحث عن 123456
            test_result2 = get_product_by_barcode('123456')
            if test_result2:
                html += f"<p class='success'>✅ البحث عن '123456': تم العثور على '{test_result2['name']}' - السعر: {test_result2['price']}</p>"
            else:
                html += "<p class='error'>❌ البحث عن '123456': لم يتم العثور على المنتج</p>"
        
        else:
            html += "<p class='error'>⚠️ لا توجد منتجات في الشيت! يرجى إضافة بعض المنتجات.</p>"
        
        html += """
            <hr>
            <h3>💡 نصائح:</h3>
            <ul>
                <li>تأكد من أن عمود 'barcode' منسق كـ "نص عادي" (Plain text)</li>
                <li>تأكد من عدم وجود مسافات قبل أو بعد أرقام الباركود</li>
                <li>جرب البحث عن 'test123' أو '123456' في التطبيق الرئيسي</li>
            </ul>
            <p><a href="/">العودة إلى التطبيق الرئيسي</a></p>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return f"""
        <h1>❌ خطأ في قراءة البيانات</h1>
        <p>حدث خطأ: {e}</p>
        <p>يرجى التحقق من تنسيق الشيت وتأكد من وجود الأعمدة: barcode, name, price</p>
        """

@app.route('/health', methods=['GET'])
def health_check():
    """فحص صحة التطبيق (لـ Render)"""
    status = {
        "status": "healthy",
        "sheets_connected": products_sheet is not None and invoices_sheet is not None,
        "products_count": len(products_sheet.get_all_records()) if products_sheet else 0,
        "timestamp": datetime.now().isoformat()
    }
    return jsonify(status)

# ==============================================
# 🚀 تشغيل التطبيق
# ==============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)