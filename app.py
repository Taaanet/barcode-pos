from flask import Flask, render_template, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json

app = Flask(__name__)

# إعداد Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# فتح الشيتات
products_sheet = client.open("Bakala_Products").sheet1
invoices_sheet = client.open("Invoices").sheet1

def get_product_by_barcode(barcode):
    records = products_sheet.get_all_records()
    for row in records:
        if str(row['barcode']) == str(barcode):
            return {"name": row['name'], "price": float(row['price'])}
    return None

def save_invoice_to_sheet(invoice_data):
    """حفظ الفاتورة في Google Sheets"""
    row = [
        invoice_data['timestamp'],
        invoice_data['total_items'],
        invoice_data['total_price'],
        invoice_data['discount'],
        invoice_data['final_price'],
        invoice_data['products_list']
    ]
    invoices_sheet.append_row(row)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_product', methods=['POST'])
def get_product():
    barcode = request.json['barcode']
    product = get_product_by_barcode(barcode)
    if product:
        return jsonify({"status": "found", "name": product['name'], "price": product['price']})
    else:
        return jsonify({"status": "not_found"})

@app.route('/save_invoice', methods=['POST'])
def save_invoice():
    data = request.json
    save_invoice_to_sheet(data)
    return jsonify({"status": "saved"})

if __name__ == '__main__':
    app.run(debug=True)