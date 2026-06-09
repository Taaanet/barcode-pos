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
import threading

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
CORS(app)

# ============== إعدادات Google Sheets ==============
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "نظام حضور الطلاب"

def get_google_client():
    """الحصول على عميل Google Sheets"""
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
        print(f"خطأ في الاتصال بـ Google Sheets: {e}")
        return None

def get_or_create_sheet():
    """الحصول على ورقة العمل أو إنشاؤها"""
    client = get_google_client()
    if not client:
        return None, None
    
    try:
        sheet = client.open(SHEET_NAME)
    except:
        sheet = client.create(SHEET_NAME)
        print(f"✅ تم إنشاء ورقة جديدة: {SHEET_NAME}")
    
    # ورقة الطلاب
    try:
        students_ws = sheet.worksheet("الطلاب")
    except:
        students_ws = sheet.add_worksheet(title="الطلاب", rows="1000", cols="20")
        headers = ['student_id', 'name', 'grade', 'class', 'phone', 'parent_phone', 'notes']
        students_ws.append_row(headers)
    
    # ورقة الحضور
    try:
        attendance_ws = sheet.worksheet("الحضور")
    except:
        attendance_ws = sheet.add_worksheet(title="الحضور", rows="10000", cols="20")
        headers = ['student_id', 'student_name', 'grade', 'class', 'date', 'time', 'status', 'timestamp']
        attendance_ws.append_row(headers)
    
    return students_ws, attendance_ws

def load_students():
    """تحميل الطلاب من Google Sheets"""
    try:
        students_ws, _ = get_or_create_sheet()
        if not students_ws:
            return []
        records = students_ws.get_all_records()
        
        fixed_records = []
        for record in records:
            fixed_record = {}
            for key, value in record.items():
                if value is None:
                    fixed_record[key] = ''
                elif isinstance(value, (int, float)):
                    fixed_record[key] = str(int(value)) if value == int(value) else str(value)
                else:
                    try:
                        fixed_record[key] = str(value)
                    except:
                        fixed_record[key] = ''
            fixed_records.append(fixed_record)
        
        return fixed_records
    except Exception as e:
        print(f"خطأ في تحميل الطلاب: {e}")
        return []

def load_attendance():
    """تحميل سجلات الحضور من Google Sheets"""
    try:
        _, attendance_ws = get_or_create_sheet()
        if not attendance_ws:
            print("⚠️ لا يمكن الوصول إلى ورقة الحضور")
            return []
        
        all_data = attendance_ws.get_all_values()
        print(f"📋 عدد صفوف الحضور في Google Sheets: {len(all_data)}")
        
        if len(all_data) <= 1:
            print("⚠️ لا توجد بيانات حضور")
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
        print(f"❌ خطأ في تحميل الحضور: {e}")
        return []

def save_attendance(record):
    """حفظ سجل حضور جديد في Google Sheets"""
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
        print(f"✅ تم حفظ سجل حضور: {record['student_name']} - {record['date']}")
        return True
    except Exception as e:
        print(f"خطأ في حفظ الحضور: {e}")
        return False

# ============== إعدادات التوقيت السعودي ==============
def get_saudi_time():
    return datetime.utcnow() + timedelta(hours=3)

def is_weekend(date):
    weekday = date.weekday()
    return weekday == 4 or weekday == 5

def is_within_daily_hours(current_time):
    start_time = time(6, 0, 0)
    end_time = time(12, 0, 0)
    return start_time <= current_time <= end_time

def can_register_attendance():
    now = get_saudi_time()
    current_time = now.time()
    current_date = now.date()
    
    if is_weekend(current_date):
        return False, "لا يمكن تسجيل الحضور في أيام العطلات (الجمعة والسبت)"
    
    if not is_within_daily_hours(current_time):
        return False, "يمكن تسجيل الحضور فقط من الساعة 6 صباحاً حتى 12 ظهراً"
    
    return True, None

def get_attendance_status():
    now = get_saudi_time()
    current_time = now.strftime("%H:%M:%S")
    deadline = "07:30:00"
    if current_time <= deadline:
        return "حاضر في الوقت", current_time
    else:
        return "متأخر", current_time

# ============== إعدادات البريد الإلكتروني ==============
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
            return False, "كلمة مرور البريد الإلكتروني غير مضبوطة"
        
        msg = Message(subject, recipients=[recipient])
        msg.html = body
        
        if attachment_path and os.path.exists(attachment_path):
            with app.open_resource(attachment_path) as fp:
                msg.attach(
                    os.path.basename(attachment_path),
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    fp.read()
                )
        
        mail.send(msg)
        return True, "تم الإرسال بنجاح"
    except Exception as e:
        return False, str(e)

# ============== بيانات المستخدمين ==============
USERS_FILE = 'users.json'

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    
    default_users = {
        'Taha_Mohamed': {
            'password': 'hetaonet0hros',
            'role': 'admin',
            'login_count': 0,
            'max_logins': None
        },
        'admin': {
            'password': 'admin123',
            'role': 'user',
            'login_count': 0,
            'max_logins': 5
        }
    }
    save_users(default_users)
    return default_users

def save_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ في حفظ المستخدمين: {e}")

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

# تحميل البيانات الأولية
students = load_students()
attendance_records = load_attendance()

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

# ============== API التسجيل (المحدث) ==============
@app.route("/api/register", methods=["POST"])
@login_required
def register_attendance():
    global attendance_records
    
    try:
        can_register, error_message = can_register_attendance()
        if not can_register:
            return jsonify({"success": False, "message": error_message})
        
        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()
        
        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})
        
        student = None
        for s in students:
            db_student_id = str(s.get('student_id', ''))
            if db_student_id == student_id:
                student = s
                break
        
        if not student:
            available_ids = [str(s.get('student_id', '')) for s in students[:5]]
            return jsonify({
                "success": False, 
                "message": f"الطالب {student_id} غير موجود. الأرقام المتاحة: {', '.join(available_ids)}"
            })
        
        status, current_time = get_attendance_status()
        now = get_saudi_time()
        current_date = now.strftime("%Y-%m-%d")
        
        # التحقق من عدم التكرار في Google Sheets
        _, attendance_ws = get_or_create_sheet()
        if attendance_ws:
            all_data = attendance_ws.get_all_values()
            for row in all_data[1:]:
                if len(row) >= 5 and row[0] == student_id and row[4] == current_date:
                    return jsonify({
                        "success": False,
                        "message": f"⚠️ {student.get('name')} مسجل مسبقاً اليوم",
                        "already_registered": True,
                        "student_name": str(student.get('name', '')),
                        "student_grade": str(student.get('grade', '')),
                        "student_class": str(student.get('class', ''))
                    })
        
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
            # تحديث الذاكرة المحلية
            attendance_records.append(new_record)
            
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

# ============== باقي APIs ==============
@app.route("/api/students_list")
@login_required
def students_list():
    return jsonify({"success": True, "data": students})

@app.route("/api/attendance_summary")
@login_required
def attendance_summary():
    today = get_saudi_time().strftime("%Y-%m-%d")
    total = len(students)
    today_records = [r for r in attendance_records if r.get('date') == today]
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
    try:
        result = []
        for student in students:
            record = None
            for r in attendance_records:
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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/absent_students_today")
@login_required
def absent_students_today():
    try:
        today = get_saudi_time().strftime("%Y-%m-%d")
        present_ids = set(str(r.get('student_id', '')) for r in attendance_records if r.get('date') == today)
        
        absent_students = []
        for student in students:
            student_id = str(student.get('student_id', ''))
            if student_id and student_id not in present_ids:
                absent_students.append({
                    'student_id': student_id,
                    'name': student.get('name', ''),
                    'grade': student.get('grade', ''),
                    'class': student.get('class', '')
                })
        
        return jsonify({"success": True, "data": absent_students, "count": len(absent_students), "date": today})
    except Exception as e:
        return jsonify({"success": False, "data": [], "error": str(e)})

@app.route("/api/top_students")
@login_required
def top_students():
    present_counts = {}
    for r in attendance_records:
        if r.get('status') in ['حاضر في الوقت', 'متأخر']:
            name = r.get('student_name')
            present_counts[name] = present_counts.get(name, 0) + 1
    sorted_students = sorted(present_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    result = [{"name": name, "count": count} for name, count in sorted_students]
    return jsonify({"success": True, "data": result})

@app.route("/api/student_report/<student_id>")
@login_required
def student_report(student_id):
    try:
        student = next((s for s in students if s.get('student_id') == student_id), None)
        if not student:
            return jsonify({"success": False, "error": "الطالب غير موجود"})
        
        records = [r for r in attendance_records if r.get('student_id') == student_id]
        records.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        present = len([r for r in records if r.get('status') == 'حاضر في الوقت'])
        late = len([r for r in records if r.get('status') == 'متأخر'])
        total = len(records)
        
        if records:
            first_date = datetime.strptime(records[-1].get('date'), "%Y-%m-%d")
            today = get_saudi_time().date()
            school_days = 0
            current = first_date
            while current.date() <= today:
                if current.weekday() not in [4, 5]:
                    school_days += 1
                current += timedelta(days=1)
        else:
            school_days = 0
        
        absent = school_days - (present + late) if school_days > 0 else 0
        attendance_rate = round((present + late) / school_days * 100, 1) if school_days > 0 else 0
        
        return jsonify({
            "success": True,
            "student_name": student.get('name'),
            "student_id": student_id,
            "grade": student.get('grade'),
            "class": student.get('class'),
            "total_days": school_days,
            "present": present,
            "late": late,
            "absent": absent if absent > 0 else 0,
            "attendance_rate": attendance_rate,
            "records": records
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/monthly_report")
@login_required
def monthly_report():
    try:
        year = int(request.args.get('year', get_saudi_time().year))
        month = int(request.args.get('month', get_saudi_time().month))
        
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)
        days_in_month = (next_month - datetime(year, month, 1)).days
        
        daily_stats = []
        for day in range(1, days_in_month + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            day_records = [r for r in attendance_records if r.get('date') == date_str]
            daily_stats.append({
                'day': day, 
                'present': len([r for r in day_records if r.get('status') == 'حاضر في الوقت']),
                'late': len([r for r in day_records if r.get('status') == 'متأخر']),
                'absent': len(students) - len(day_records)
            })
        
        return jsonify({
            "success": True, 
            "daily_stats": daily_stats, 
            "total_present": sum(d['present'] for d in daily_stats),
            "total_late": sum(d['late'] for d in daily_stats), 
            "days_in_month": days_in_month, 
            "month": month, 
            "year": year
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_chart")
@login_required
def attendance_chart():
    today = get_saudi_time().strftime("%Y-%m-%d")
    today_records = [r for r in attendance_records if r.get('date') == today]
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
    total = len(students)
    
    today_records = [r for r in attendance_records if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = total - (present + late)
    percentage = round((present + late) / total * 100, 1) if total > 0 else 0
    
    present_counts = {}
    for r in attendance_records:
        if r.get('status') in ['حاضر في الوقت', 'متأخر']:
            name = r.get('student_name')
            present_counts[name] = present_counts.get(name, 0) + 1
    best_student = max(present_counts.items(), key=lambda x: x[1])[0] if present_counts else "لا يوجد"
    
    late_counts = {}
    for r in attendance_records:
        if r.get('status') == 'متأخر':
            name = r.get('student_name')
            late_counts[name] = late_counts.get(name, 0) + 1
    most_late = max(late_counts.items(), key=lambda x: x[1])[0] if late_counts else "لا يوجد"
    
    return jsonify({
        "success": True, 
        "percentage": percentage, 
        "present_today": present + late,
        "present": present,
        "late": late,
        "absent": absent,
        "total_students": total, 
        "best_student": best_student,
        "most_late_student": most_late,
        "total_records": len(attendance_records)
    })

# ============== APIs التصدير ==============
@app.route("/api/export_today_excel")
@login_required
def export_today_excel():
    try:
        today = get_saudi_time().strftime("%Y-%m-%d")
        filename = f"attendance_report_{today}.xlsx"
        result = []
        for student in students:
            record = None
            for r in attendance_records:
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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_monthly_excel")
@login_required
def export_monthly_excel():
    try:
        year = request.args.get('year', get_saudi_time().year)
        month = request.args.get('month', get_saudi_time().month)
        filename = f"monthly_report_{year}_{month}.xlsx"
        monthly_stats = []
        for student in students:
            student_records = [r for r in attendance_records if r.get('student_id') == student.get('student_id')]
            present = len([r for r in student_records if r.get('status') == 'حاضر في الوقت'])
            late = len([r for r in student_records if r.get('status') == 'متأخر'])
            monthly_stats.append({
                'رقم الطالب': student.get('student_id'), 
                'اسم الطالب': student.get('name'),
                'الصف': student.get('grade'), 
                'الشعبة': student.get('class'),
                'عدد أيام الحضور': present, 
                'عدد أيام التأخير': late,
                'الغياب': len(student_records) - (present + late),
                'نسبة الحضور': round((present + late) / len(student_records) * 100, 1) if len(student_records) > 0 else 0
            })
        df = pd.DataFrame(monthly_stats)
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_attendance/<date>")
@login_required
def export_attendance(date):
    try:
        filename = f"attendance_{date}.xlsx"
        
        result = []
        for student in students:
            record = None
            for r in attendance_records:
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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_student_excel/<student_id>")
@login_required
def export_student_excel(student_id):
    try:
        student = next((s for s in students if s.get('student_id') == student_id), None)
        if not student:
            return jsonify({"success": False, "error": "الطالب غير موجود"})
        
        filename = f"student_{student_id}_report.xlsx"
        
        records = [r for r in attendance_records if r.get('student_id') == student_id]
        records.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        df = pd.DataFrame(records)
        df.to_excel(filename, index=False, engine='openpyxl')
        
        return send_file(filename, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_all_data")
@login_required
def export_all_data():
    try:
        if not attendance_records:
            return jsonify({"success": False, "message": "لا توجد بيانات"})
        filename = f"all_attendance_data_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"
        df = pd.DataFrame(attendance_records)
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ============== APIs إدارة البيانات ==============
@app.route("/api/upload_local_students")
@login_required
def upload_local_students():
    try:
        if not os.path.exists('students.xlsx'):
            return jsonify({"success": False, "message": "ملف students.xlsx غير موجود"})
        
        df = pd.read_excel('students.xlsx')
        records = df.to_dict('records')
        
        students_ws, _ = get_or_create_sheet()
        if not students_ws:
            return jsonify({"success": False, "message": "فشل الاتصال بـ Google Sheets"})
        
        all_rows = students_ws.get_all_values()
        if len(all_rows) > 1:
            for row_num in range(len(all_rows), 1, -1):
                students_ws.delete_rows(row_num)
        
        count = 0
        for record in records:
            try:
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
            except Exception as e:
                print(f"خطأ: {e}")
        
        global students
        students = load_students()
        
        return jsonify({"success": True, "message": f"✅ تم إضافة {count} طالب!", "total_students": len(students)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/init_database")
@login_required
def init_database():
    try:
        students_ws, _ = get_or_create_sheet()
        if not students_ws:
            return jsonify({"error": "لا يمكن الاتصال بـ Google Sheets"})
        
        all_rows = students_ws.get_all_values()
        if len(all_rows) > 1:
            for row_num in range(len(all_rows), 1, -1):
                students_ws.delete_rows(row_num)
        
        sample_students = [
            ['1150436838', 'أحمد محمد', 'الأول الثانوي', 'أ'],
            ['1152217368', 'خالد عبدالله', 'الأول الثانوي', 'أ'],
            ['1152327969', 'سارة أحمد', 'الأول الثانوي', 'ب'],
            ['1152502371', 'محمد إبراهيم', 'الأول الثانوي', 'ب'],
            ['1153472889', 'نورة سعيد', 'الأول الثانوي', 'ج'],
        ]
        
        for student in sample_students:
            students_ws.append_row(student)
        
        global students
        students = load_students()
        
        return jsonify({
            "success": True,
            "message": f"✅ تم إضافة {len(sample_students)} طالب تجريبي",
            "count": len(students)
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/refresh_students")
@login_required
def refresh_students():
    global students
    students = load_students()
    return jsonify({"success": True, "message": f"تم تحديث بيانات الطلاب", "count": len(students)})

@app.route("/api/refresh_attendance")
@login_required
def refresh_attendance():
    global attendance_records
    attendance_records = load_attendance()
    return jsonify({"success": True, "message": f"تم تحديث سجلات الحضور", "count": len(attendance_records)})

@app.route("/api/refresh_all")
@login_required
def refresh_all():
    """تحديث جميع البيانات"""
    try:
        global students, attendance_records
        students = load_students()
        attendance_records = load_attendance()
        return jsonify({
            "success": True,
            "message": "تم تحديث جميع البيانات",
            "students_count": len(students),
            "attendance_count": len(attendance_records)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/clear_students")
@login_required
def clear_students():
    try:
        students_ws, _ = get_or_create_sheet()
        if not students_ws:
            return jsonify({"error": "لا يمكن الاتصال"})
        
        all_rows = students_ws.get_all_values()
        if len(all_rows) > 1:
            for row_num in range(len(all_rows), 1, -1):
                students_ws.delete_rows(row_num)
        
        global students
        students = []
        return jsonify({"success": True, "message": "تم مسح جميع الطلاب"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/clear_attendance")
@login_required
def clear_attendance():
    global attendance_records
    attendance_records = []
    return jsonify({"success": True, "message": "تم مسح سجلات الحضور"})

@app.route("/api/check_storage")
@login_required
def check_storage():
    return jsonify({
        "using_google_sheets": True,
        "attendance_count": len(attendance_records),
        "students_count": len(students)
    })

@app.route("/api/debug_students")
@login_required
def debug_students():
    return jsonify({"success": True, "count": len(students), "students": students[:10]})

@app.route("/api/debug_attendance")
@login_required
def debug_attendance():
    try:
        _, attendance_ws = get_or_create_sheet()
        if not attendance_ws:
            return jsonify({"error": "لا يمكن الاتصال بورقة الحضور"})
        
        all_records = attendance_ws.get_all_records()
        all_dates = sorted(list(set(record.get('date', '') for record in all_records)))
        
        return jsonify({
            "success": True,
            "total_records_in_sheet": len(all_records),
            "available_dates": all_dates,
            "sample_records": all_records[:10]
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/find_student/<student_id>")
@login_required
def find_student(student_id):
    try:
        search_id = str(student_id).strip()
        found = None
        for s in students:
            if str(s.get('student_id', '')) == search_id:
                found = s
                break
        
        if found:
            return jsonify({"success": True, "found": True, "student": found})
        else:
            available_ids = [str(s.get('student_id', '')) for s in students[:5]]
            return jsonify({"success": False, "found": False, "searched_for": search_id, "sample_ids": available_ids})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/stats")
@login_required
def stats():
    return jsonify({
        "success": True, 
        "students_count": len(students), 
        "attendance_count": len(attendance_records), 
        "storage": "google_sheets"
    })

@app.route("/api/saudi_time")
@login_required
def saudi_time():
    now = get_saudi_time()
    return jsonify({
        "success": True,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "is_weekend": is_weekend(now.date()),
        "can_register": can_register_attendance()[0]
    })

# ============== تحديث تلقائي ==============
@app.route("/api/auto_refresh")
def auto_refresh():
    try:
        global students, attendance_records
        students = load_students()
        attendance_records = load_attendance()
        return jsonify({
            "success": True,
            "students_count": len(students),
            "attendance_count": len(attendance_records),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/force_sync")
@login_required
def force_sync():
    try:
        global students, attendance_records
        students = load_students()
        attendance_records = load_attendance()
        
        return jsonify({
            "success": True,
            "message": "تمت المزامنة بنجاح",
            "students_count": len(students),
            "attendance_count": len(attendance_records)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/full_reload")
@login_required
def full_reload():
    try:
        global students, attendance_records
        students = load_students()
        attendance_records = load_attendance()
        
        return jsonify({
            "success": True,
            "message": "تم إعادة تحميل جميع البيانات بنجاح",
            "students_count": len(students),
            "attendance_count": len(attendance_records)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    print("=" * 50)
    print("🔄 جاري تحميل البيانات من Google Sheets...")
    
    students = load_students()
    attendance_records = load_attendance()
    
    print(f"📚 تم تحميل {len(students)} طالب")
    print(f"📋 تم تحميل {len(attendance_records)} سجل حضور")
    print("=" * 50)
    print("🚀 نظام الحضور يعمل الآن مع Google Sheets!")
    print("⏰ وقت الدوام: 6:00 صباحاً - 12:00 ظهراً (بتوقيت السعودية)")
    print("📅 أيام العطلات: الجمعة والسبت")
    print("=" * 50)
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)