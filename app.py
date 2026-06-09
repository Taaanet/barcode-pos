from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_cors import CORS
from flask_mail import Mail, Message
from datetime import datetime, timedelta, time
import os
import json
import pandas as pd
from functools import wraps
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
CORS(app)

# ============== إعدادات Google Sheets ==============
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "نظام حضور الطلاب"

def get_google_client():
    try:
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            creds_dict = json.loads(creds_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
            return gspread.authorize(creds)
        else:
            print("⚠️ لم يتم العثور على GOOGLE_CREDENTIALS_JSON")
            return None
    except Exception as e:
        print(f"خطأ في الاتصال: {e}")
        return None

def get_or_create_sheet():
    client = get_google_client()
    if not client:
        return None, None
    
    try:
        sheet = client.open(SHEET_NAME)
    except:
        sheet = client.create(SHEET_NAME)
        print(f"✅ تم إنشاء ورقة جديدة: {SHEET_NAME}")
    
    try:
        students_ws = sheet.worksheet("الطلاب")
    except:
        students_ws = sheet.add_worksheet(title="الطلاب", rows="1000", cols="20")
        headers = ['student_id', 'name', 'grade', 'class', 'phone', 'parent_phone', 'notes']
        students_ws.append_row(headers)
    
    try:
        attendance_ws = sheet.worksheet("الحضور")
    except:
        attendance_ws = sheet.add_worksheet(title="الحضور", rows="10000", cols="20")
        headers = ['student_id', 'student_name', 'grade', 'class', 'date', 'time', 'status', 'timestamp']
        attendance_ws.append_row(headers)
    
    return students_ws, attendance_ws

# ============== القراءة المباشرة ==============
def get_live_attendance():
    """قراءة سجلات الحضور مباشرة"""
    try:
        _, attendance_ws = get_or_create_sheet()
        if not attendance_ws:
            return []
        
        all_data = attendance_ws.get_all_values()
        print(f"📋 عدد الصفوف في Google Sheets: {len(all_data)}")
        
        if len(all_data) <= 1:
            return []
        
        headers = all_data[0]
        records = []
        for row in all_data[1:]:
            if len(row) >= 1 and row[0]:
                record = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        record[header] = row[i]
                    else:
                        record[header] = ''
                records.append(record)
        
        print(f"✅ تم تحميل {len(records)} سجل حضور")
        return records
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return []

def get_live_students():
    """قراءة الطلاب مباشرة"""
    try:
        students_ws, _ = get_or_create_sheet()
        if not students_ws:
            return []
        
        all_data = students_ws.get_all_values()
        if len(all_data) <= 1:
            return []
        
        headers = all_data[0]
        records = []
        for row in all_data[1:]:
            if len(row) >= 2 and row[0]:
                record = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        record[header] = row[i]
                    else:
                        record[header] = ''
                records.append(record)
        return records
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return []

def save_attendance(record):
    try:
        _, attendance_ws = get_or_create_sheet()
        if not attendance_ws:
            return False
        
        attendance_ws.append_row([
            record['student_id'],
            record['student_name'],
            record['grade'],
            record['class'],
            record['date'],
            record['time'],
            record['status'],
            record['timestamp']
        ])
        print(f"✅ تم حفظ: {record['student_name']}")
        return True
    except Exception as e:
        print(f"❌ خطأ في الحفظ: {e}")
        return False

# ============== التوقيت السعودي ==============
def get_saudi_time():
    return datetime.utcnow() + timedelta(hours=3)

def is_weekend(date):
    return date.weekday() == 4 or date.weekday() == 5

def is_within_daily_hours(current_time):
    start_time = time(6, 0, 0)
    end_time = time(12, 0, 0)
    return start_time <= current_time <= end_time

def can_register_attendance():
    now = get_saudi_time()
    if is_weekend(now.date()):
        return False, "لا يمكن تسجيل الحضور في أيام العطلات (الجمعة والسبت)"
    if not is_within_daily_hours(now.time()):
        return False, "يمكن تسجيل الحضور فقط من الساعة 6 صباحاً حتى 12 ظهراً"
    return True, None

def get_attendance_status():
    now = get_saudi_time()
    current_time = now.strftime("%H:%M:%S")
    return ("حاضر في الوقت", current_time) if current_time <= "07:30:00" else ("متأخر", current_time)

# ============== البريد الإلكتروني ==============
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'taaanet@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = 'taaanet@gmail.com'

mail = Mail(app)

def send_report_email(recipient, subject, body, attachment_path=None):
    try:
        if not app.config['MAIL_PASSWORD']:
            return False, "كلمة مرور البريد غير مضبوطة"
        msg = Message(subject, recipients=[recipient])
        msg.html = body
        if attachment_path and os.path.exists(attachment_path):
            with app.open_resource(attachment_path) as fp:
                msg.attach(os.path.basename(attachment_path), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', fp.read())
        mail.send(msg)
        return True, "تم الإرسال"
    except Exception as e:
        return False, str(e)

# ============== المستخدمين ==============
USERS_FILE = 'users.json'

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    
    default_users = {
        'Taha_Mohamed': {'password': 'hetaonet0hros', 'role': 'admin', 'login_count': 0, 'max_logins': None},
        'admin': {'password': 'admin123', 'role': 'user', 'login_count': 0, 'max_logins': 5}
    }
    save_users(default_users)
    return default_users

def save_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ: {e}")

def can_login(username):
    users = load_users()
    if username not in users:
        return False, "اسم المستخدم غير موجود"
    user = users[username]
    if user['role'] == 'admin':
        return True, None
    if user['max_logins'] is not None and user['login_count'] >= user['max_logins']:
        return False, f"لقد تجاوزت الحد المسموح به ({user['max_logins']} مرات)"
    return True, None

def increment_login_count(username):
    users = load_users()
    if username in users and users[username]['role'] != 'admin':
        users[username]['login_count'] = users[username].get('login_count', 0) + 1
        save_users(users)

def get_remaining_logins(username):
    users = load_users()
    if username not in users:
        return 0
    user = users[username]
    if user['role'] == 'admin':
        return "غير محدود"
    max_logins = user.get('max_logins', 5)
    used = user.get('login_count', 0)
    return max(max_logins - used, 0)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============== صفحات المصادقة ==============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = load_users()
        if username in users and users[username]['password'] == password:
            can_login_flag, message = can_login(username)
            if not can_login_flag:
                return render_template('login.html', error=message)
            increment_login_count(username)
            session['logged_in'] = True
            session['username'] = username
            session['role'] = users[username]['role']
            session['remaining_logins'] = get_remaining_logins(username)
            return redirect(url_for('home'))
        return render_template('login.html', error="اسم المستخدم أو كلمة المرور غير صحيحة")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/users_list')
@login_required
def users_list():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    users = load_users()
    users_data = []
    for username, data in users.items():
        users_data.append({
            'username': username,
            'role': data['role'],
            'login_count': data.get('login_count', 0),
            'max_logins': data.get('max_logins', 'غير محدود') if data['role'] == 'admin' else data.get('max_logins', 5),
            'remaining': get_remaining_logins(username)
        })
    return render_template('users_list.html', users=users_data)

@app.route('/reset_logins/<username>')
@login_required
def reset_logins(username):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    users = load_users()
    if username in users:
        users[username]['login_count'] = 0
        save_users(users)
        return jsonify({"success": True, "message": f"تم إعادة تعيين {username}"})
    return jsonify({"success": False, "message": "المستخدم غير موجود"})

# ============== الصفحات الرئيسية ==============
@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/scan")
@login_required
def scan():
    return render_template("scan.html")

@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

# ============== API التسجيل ==============
@app.route("/api/register", methods=["POST"])
@login_required
def register_attendance():
    try:
        can_register, error_message = can_register_attendance()
        if not can_register:
            return jsonify({"success": False, "message": error_message})
        
        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()
        
        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})
        
        students = get_live_students()
        student = None
        for s in students:
            if str(s.get('student_id', '')) == student_id:
                student = s
                break
        
        if not student:
            return jsonify({"success": False, "message": f"الطالب {student_id} غير موجود"})
        
        status, current_time = get_attendance_status()
        now = get_saudi_time()
        current_date = now.strftime("%Y-%m-%d")
        
        # التحقق من عدم التكرار
        attendance_records = get_live_attendance()
        for record in attendance_records:
            if record.get('student_id') == student_id and record.get('date') == current_date:
                return jsonify({"success": False, "message": f"⚠️ {student.get('name')} مسجل مسبقاً اليوم"})
        
        new_record = {
            'student_id': student_id,
            'student_name': str(student.get('name', '')),
            'grade': str(student.get('grade', '')),
            'class': str(student.get('class', '')),
            'date': current_date,
            'time': current_time,
            'status': status,
            'timestamp': now.isoformat()
        }
        
        if save_attendance(new_record):
            return jsonify({
                "success": True,
                "message": f"✅ تم تسجيل حضور {student.get('name')} - {status} الساعة {current_time}",
                "student_name": str(student.get('name', '')),
                "student_grade": str(student.get('grade', '')),
                "student_class": str(student.get('class', '')),
                "time": current_time,
                "date": current_date,
                "status": status
            })
        else:
            return jsonify({"success": False, "message": "فشل حفظ البيانات"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============== API التقارير ==============
@app.route("/api/students_list")
@login_required
def students_list():
    students = get_live_students()
    return jsonify({"success": True, "data": students})

@app.route("/api/attendance_summary")
@login_required
def attendance_summary():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()
    
    total = len(students)
    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = total - (present + late)
    percentage = round((present + late) / total * 100, 1) if total > 0 else 0
    
    return jsonify({
        "success": True,
        "total_students": total,
        "present": present,
        "late": late,
        "absent": absent if absent > 0 else 0,
        "percentage": percentage,
        "date": today
    })

@app.route("/api/attendance_details/<date>")
@login_required
def attendance_details(date):
    students = get_live_students()
    attendance = get_live_attendance()
    
    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == date:
                record = r
                break
        result.append({
            'student_id': student.get('student_id'),
            'student_name': student.get('name'),
            'grade': student.get('grade'),
            'class': student.get('class'),
            'status': record.get('status') if record else 'غائب',
            'time': record.get('time') if record else '-'
        })
    return jsonify({"success": True, "data": result})

@app.route("/api/absent_students_today")
@login_required
def absent_students_today():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()
    
    present_ids = set(r.get('student_id') for r in attendance if r.get('date') == today)
    absent = [s for s in students if s.get('student_id') not in present_ids]
    return jsonify({"success": True, "data": absent, "count": len(absent), "date": today})

@app.route("/api/top_students")
@login_required
def top_students():
    attendance = get_live_attendance()
    counts = {}
    for r in attendance:
        if r.get('status') in ['حاضر في الوقت', 'متأخر']:
            name = r.get('student_name')
            counts[name] = counts.get(name, 0) + 1
    sorted_students = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return jsonify({"success": True, "data": [{"name": n, "count": c} for n, c in sorted_students]})

@app.route("/api/student_report/<student_id>")
@login_required
def student_report(student_id):
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})
    
    attendance = get_live_attendance()
    records = [r for r in attendance if r.get('student_id') == student_id]
    records.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    return jsonify({
        "success": True,
        "student_name": student.get('name'),
        "student_id": student_id,
        "grade": student.get('grade'),
        "class": student.get('class'),
        "records": records
    })

@app.route("/api/monthly_report")
@login_required
def monthly_report():
    year = int(request.args.get('year', get_saudi_time().year))
    month = int(request.args.get('month', get_saudi_time().month))
    students = get_live_students()
    attendance = get_live_attendance()
    
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    days = (next_month - datetime(year, month, 1)).days
    
    stats = []
    for day in range(1, days + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        day_records = [r for r in attendance if r.get('date') == date_str]
        stats.append({
            'day': day,
            'present': len([r for r in day_records if r.get('status') == 'حاضر في الوقت']),
            'late': len([r for r in day_records if r.get('status') == 'متأخر']),
            'absent': len(students) - len(day_records)
        })
    return jsonify({"success": True, "daily_stats": stats})

@app.route("/api/attendance_chart")
@login_required
def attendance_chart():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()
    
    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = len(students) - (present + late)
    return jsonify({
        "success": True,
        "labels": ["حاضر في الوقت", "متأخر", "غائب"],
        "data": [present, late, absent],
        "colors": ["#28a745", "#fd7e14", "#dc3545"]
    })

@app.route("/api/dashboard_stats")
@login_required
def dashboard_stats():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()
    
    total = len(students)
    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = total - (present + late)
    percentage = round((present + late) / total * 100, 1) if total > 0 else 0
    
    return jsonify({
        "success": True,
        "percentage": percentage,
        "present_today": present + late,
        "present": present,
        "late": late,
        "absent": absent,
        "total_students": total,
        "total_records": len(attendance)
    })

# ============== APIs التصدير ==============
@app.route("/api/export_today_excel")
@login_required
def export_today_excel():
    today = get_saudi_time().strftime("%Y-%m-%d")
    filename = f"attendance_{today}.xlsx"
    students = get_live_students()
    attendance = get_live_attendance()
    
    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == today:
                record = r
                break
        result.append({
            'رقم الطالب': student.get('student_id'),
            'اسم الطالب': student.get('name'),
            'الصف': student.get('grade'),
            'الشعبة': student.get('class'),
            'وقت التسجيل': record.get('time') if record else '-',
            'الحالة': record.get('status') if record else 'غائب'
        })
    df = pd.DataFrame(result)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

@app.route("/api/export_attendance/<date>")
@login_required
def export_attendance(date):
    filename = f"attendance_{date}.xlsx"
    students = get_live_students()
    attendance = get_live_attendance()
    
    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == date:
                record = r
                break
        result.append({
            'رقم الطالب': student.get('student_id'),
            'اسم الطالب': student.get('name'),
            'الصف': student.get('grade'),
            'الشعبة': student.get('class'),
            'وقت التسجيل': record.get('time') if record else '-',
            'الحالة': record.get('status') if record else 'غائب'
        })
    df = pd.DataFrame(result)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

@app.route("/api/export_student_excel/<student_id>")
@login_required
def export_student_excel(student_id):
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})
    
    attendance = get_live_attendance()
    records = [r for r in attendance if r.get('student_id') == student_id]
    records.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    filename = f"student_{student_id}_report.xlsx"
    df = pd.DataFrame(records)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

# ============== APIs إدارة البيانات ==============
@app.route("/api/upload_local_students")
@login_required
def upload_local_students():
    if not os.path.exists('students.xlsx'):
        return jsonify({"success": False, "message": "ملف students.xlsx غير موجود"})
    
    df = pd.read_excel('students.xlsx')
    records = df.to_dict('records')
    
    students_ws, _ = get_or_create_sheet()
    if not students_ws:
        return jsonify({"success": False, "message": "فشل الاتصال"})
    
    all_rows = students_ws.get_all_values()
    if len(all_rows) > 1:
        for i in range(len(all_rows), 1, -1):
            students_ws.delete_rows(i)
    
    count = 0
    for record in records:
        students_ws.append_row([
            str(record.get('student_id', '')),
            str(record.get('name', '')),
            str(record.get('grade', '')),
            str(record.get('class', '')),
            str(record.get('phone', '')),
            str(record.get('parent_phone', '')),
            str(record.get('notes', ''))
        ])
        count += 1
    
    return jsonify({"success": True, "message": f"✅ تم إضافة {count} طالب"})

@app.route("/api/refresh_all")
@login_required
def refresh_all():
    students = get_live_students()
    attendance = get_live_attendance()
    return jsonify({
        "success": True,
        "students_count": len(students),
        "attendance_count": len(attendance)
    })

@app.route("/api/direct_test")
@login_required
def direct_test():
    _, attendance_ws = get_or_create_sheet()
    if not attendance_ws:
        return jsonify({"error": "لا يمكن الوصول"})
    
    all_data = attendance_ws.get_all_values()
    return jsonify({
        "success": True,
        "total_rows": len(all_data),
        "headers": all_data[0] if all_data else [],
        "sample_data": all_data[1:11] if len(all_data) > 1 else []
    })

@app.route("/api/clear_attendance")
@login_required
def clear_attendance():
    _, attendance_ws = get_or_create_sheet()
    if attendance_ws:
        all_rows = attendance_ws.get_all_values()
        if len(all_rows) > 1:
            for i in range(len(all_rows), 1, -1):
                attendance_ws.delete_rows(i)
    return jsonify({"success": True, "message": "تم مسح سجلات الحضور"})

@app.route("/api/stats")
@login_required
def stats():
    students = get_live_students()
    attendance = get_live_attendance()
    return jsonify({
        "success": True,
        "students_count": len(students),
        "attendance_count": len(attendance),
        "storage": "google_sheets"
    })

@app.route("/api/saudi_time")
@login_required
def saudi_time():
    now = get_saudi_time()
    return jsonify({
        "success": True,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "is_weekend": is_weekend(now.date()),
        "can_register": can_register_attendance()[0]
    })

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print("=" * 50)
    print("🚀 نظام الحضور يعمل الآن!")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)