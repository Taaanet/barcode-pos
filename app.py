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
    print("📌 طول المتغير:", len(env_var), "حرف")
    print("📌 أول 50 حرف:", env_var[:50], "...")
    
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
    
    # اختبار قراءة صف واحد
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
# باقي دوال التطبيق (كما هي)
# ==============================================

def get_product_by_barcode(barcode):
    if products_sheet is None:
        return None
    try:
        records = products_sheet.get_all_records()
        for row in records:
            if str(row['barcode']) == str(barcode):
                return {"name": row['name'], "price": float(row['price'])}
        return None
    except Exception as e:
        print(f"❌ خطأ في البحث: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_product', methods=['POST'])
def get_product():
    data = request.json
    barcode = data.get('barcode')
    product = get_product_by_barcode(barcode)
    if product:
        return jsonify({"status": "found", "name": product['name'], "price": product['price']})
    else:
        return jsonify({"status": "not_found"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)