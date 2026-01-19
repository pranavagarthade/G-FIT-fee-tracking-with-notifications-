from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify, send_file
from flask_pymongo import PyMongo
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from collections import defaultdict
from bson import ObjectId  
from functools import wraps
import os
from dotenv import load_dotenv
from flask_mail import Mail, Message
from flask_apscheduler import APScheduler
import requests
import json
from pymongo import MongoClient
from werkzeug.utils import secure_filename
import pandas as pd
import io

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configuration - ALL CONFIG AT THE TOP
app.config["MONGO_URI"] = "mongodb://localhost:27017/fitness_db"
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'fitnessgeeta@gmail.com'
app.config['MAIL_PASSWORD'] = 'txdjuwefdxjkrpng'
app.config['MAIL_DEFAULT_SENDER'] = 'fitnessgeeta@gmail.com'

# Scheduler Configuration
class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())

# Initialize extensions
mongo = PyMongo(app)
mail = Mail(app)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# MongoDB Setup (for attendance)
client = MongoClient("mongodb://localhost:27017/")
db = client["fitness_app"]
attendance_collection = db["attendance"]

# Create uploads folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Zoom API Credentials
ZOOM_API_KEY = "dbwb3gMIRdGZ8AuZYBGCw"
ZOOM_API_SECRET = "5CcKa3lpnHS8aypS5xLuaiQ8wMEV5dLr"
MEETING_ID = "4945909109"

# Membership pricing
membership_pricing = {
    "1 Month": 2000,
    "3 Months": 5400,
    "6 Months": 10200
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

# Admin credentials
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_membership_expiry(start_date, duration):
    """Calculate membership expiry date based on duration"""
    duration_map = {
        "1 Month": timedelta(days=30),
        "3 Months": timedelta(days=90),
        "6 Months": timedelta(days=180),
        "1 Year": timedelta(days=365),
        "1 month": timedelta(days=30),
        "3 months": timedelta(days=90),
        "6 months": timedelta(days=180),
        "1 year": timedelta(days=365)
    }
    return start_date + duration_map.get(duration, timedelta(days=30))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('You must log in first.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# ZOOM ATTENDANCE FUNCTIONS
# ============================================================================

def get_zoom_participants(meeting_id):
    url = f"https://api.zoom.us/v2/report/meetings/{meeting_id}/participants"
    headers = {
        "Authorization": f"Bearer {ZOOM_API_KEY}",
        "Content-Type": "application/json",
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json().get("participants", [])
    else:
        print("Error fetching participants:", response.json())
        return []

def mark_attendance():
    participants = get_zoom_participants(MEETING_ID)
    date_today = datetime.now().strftime("%Y-%m-%d")

    for participant in participants:
        student_name = participant.get("name")
        student_email = participant.get("user_email")

        if student_email:
            attendance_data = {
                "date": date_today,
                "batch": "5:00 to 6:00 AM",
                "student_name": student_name,
                "email": student_email,
                "status": "Present",
            }
            attendance_collection.insert_one(attendance_data)
            print(f"Marked present: {student_name} ({student_email})")


# ============================================================================
# EMAIL FUNCTIONS
# ============================================================================

def send_email_notification(subject, recipients, body):
    try:
        msg = Message(subject, recipients=recipients)
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_expiry_email(student):
    try:
        msg = Message(
            subject="Membership Expired - Geetanjali Yoga & Fitness Zone",
            recipients=[student['email']],
            body=f"""Hi {student['name']},

Your membership expired on {student['membership_expiry'].strftime('%d %B %Y')}.
We love to have you back!

To renew your plan, please contact:
📞 8591727736
📧 fitnessgeeta@gmail.com

Stay fit,
Geetanjali Yoga & Fitness Zone
"""
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def check_membership_expiry():
    current_date = datetime.now()
    expiry_threshold = current_date + timedelta(days=2)
    
    # Notify expiring soon
    expiring_members = mongo.db.students.find({
        "membership_expiry": {"$lt": expiry_threshold, "$gte": current_date}
    })

    for member in expiring_members:
        if member.get('email'):
            send_email_notification(
                "Membership Expiry Reminder",
                [member['email']],
                f"Dear {member['name']}, your membership will expire on {member['membership_expiry'].date()}. Please renew it soon!"
            )

    # Notify just expired (in the last 1 day)
    just_expired = mongo.db.students.find({
        "membership_expiry": {"$lt": current_date, "$gte": current_date - timedelta(days=1)}
    })

    for member in just_expired:
        if member.get('email'):
            send_email_notification(
                "Membership Expired",
                [member['email']],
                f"Dear {member['name']}, your membership expired on {member['membership_expiry'].date()}. Please renew to continue attending classes."
            )


# ============================================================================
# SCHEDULED TASKS
# ============================================================================

@scheduler.task('cron', id='daily_expiry_email_job', hour=7)
def daily_expiry_email_job():
    with app.app_context():
        trigger_expiry_emails()


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))


# ============================================================================
# DASHBOARD ROUTES
# ============================================================================

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    total_students = mongo.db.students.count_documents({})
    expired_memberships = mongo.db.students.count_documents({"membership_expiry": {"$lt": datetime.now()}})
    pending_fees = mongo.db.fees.count_documents({"status": "Pending"})
    
    return render_template('dashboard.html', 
                         total_students=total_students,
                         expired_memberships=expired_memberships, 
                         pending_fees=pending_fees)


# ============================================================================
# STUDENT ROUTES
# ============================================================================
@app.route('/students')
@login_required
def students():
    students = list(mongo.db.students.find())
    current_time = datetime.now()
    return render_template('students.html', students=students, current_time=current_time)

@app.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            membership_duration = request.form.get('membership_duration')
            
            # Validate required fields
            if not all([name, email, phone, membership_duration]):
                flash('All fields are required!', 'error')
                return redirect(url_for('add_student'))
            
            # Check if email already exists
            existing_student = mongo.db.students.find_one({'email': email})
            if existing_student:
                flash('A student with this email already exists!', 'error')
                return redirect(url_for('add_student'))
            
            # Calculate membership expiry
            current_date = datetime.now()
            membership_expiry = calculate_membership_expiry(current_date, membership_duration)
            amount_paid = membership_pricing.get(membership_duration, 0)
            
            # Insert student
            student_id = mongo.db.students.insert_one({
                'name': name,
                'email': email,
                'phone': phone,
                'membership_duration': membership_duration,
                'membership_expiry': membership_expiry,
                'created_at': current_date
            }).inserted_id
            
            # Add fee record
            mongo.db.fees.insert_one({
                'student_id': ObjectId(student_id),
                'amount_paid': amount_paid,
                'payment_date': current_date,
                'membership_duration': membership_duration,
                'membership_expiry': membership_expiry,
                'status': 'Paid'
            })
            
            flash(f'Student {name} added successfully!', 'success')
            return redirect(url_for('students'))
            
        except Exception as e:
            flash(f'Error adding student: {str(e)}', 'error')
            return redirect(url_for('add_student'))
    
    return render_template('add_student.html', membership_pricing=membership_pricing)

@app.route('/students/edit/<student_id>', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    student = mongo.db.students.find_one({'_id': ObjectId(student_id)})
    
    if not student:
        flash('Student not found!', 'error')
        return redirect(url_for('students'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            membership_duration = request.form.get('membership_duration')
            
            # Check if email is being changed and if it already exists
            if email != student['email']:
                existing = mongo.db.students.find_one({'email': email})
                if existing:
                    flash('A student with this email already exists!', 'error')
                    return redirect(url_for('edit_student', student_id=student_id))
            
            # Calculate new expiry if duration changed
            if membership_duration != student.get('membership_duration'):
                current_date = datetime.now()
                membership_expiry = calculate_membership_expiry(current_date, membership_duration)
                amount_paid = membership_pricing.get(membership_duration, 0)
                
                # Add new fee record
                mongo.db.fees.insert_one({
                    'student_id': ObjectId(student_id),
                    'amount_paid': amount_paid,
                    'payment_date': current_date,
                    'membership_duration': membership_duration,
                    'membership_expiry': membership_expiry,
                    'status': 'Paid'
                })
            else:
                membership_expiry = student.get('membership_expiry')
            
            # Update student
            mongo.db.students.update_one(
                {'_id': ObjectId(student_id)},
                {
                    '$set': {
                        'name': name,
                        'email': email,
                        'phone': phone,
                        'membership_duration': membership_duration,
                        'membership_expiry': membership_expiry,
                        'updated_at': datetime.now()
                    }
                }
            )
            
            flash(f'Student {name} updated successfully!', 'success')
            return redirect(url_for('students'))
            
        except Exception as e:
            flash(f'Error updating student: {str(e)}', 'error')
            return redirect(url_for('edit_student', student_id=student_id))
    
    return render_template('edit_student.html', student=student, membership_pricing=membership_pricing)

@app.route('/students/delete/<student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    try:
        student = mongo.db.students.find_one({'_id': ObjectId(student_id)})
        if student:
            # Delete associated fee records
            mongo.db.fees.delete_many({'student_id': ObjectId(student_id)})
            # Delete student
            mongo.db.students.delete_one({'_id': ObjectId(student_id)})
            flash(f'Student {student["name"]} deleted successfully!', 'success')
        else:
            flash('Student not found!', 'error')
    except Exception as e:
        flash(f'Error deleting student: {str(e)}', 'error')
    
    return redirect(url_for('students'))

@app.route('/students/notify/<student_id>', methods=['POST'])
@login_required
def notify_student(student_id):
    try:
        student = mongo.db.students.find_one({'_id': ObjectId(student_id)})
        if student:
            # Here you would implement actual email/SMS notification
            # For now, we'll just flash a message
            flash(f'Notification sent to {student["name"]} at {student["email"]}', 'success')
        else:
            flash('Student not found!', 'error')
    except Exception as e:
        flash(f'Error sending notification: {str(e)}', 'error')
    
    return redirect(url_for('students'))

@app.route('/students/import', methods=['POST'])
@login_required
def import_students():
    """Import students from Excel/CSV file with flexible column mapping"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Invalid file type. Please upload .xlsx, .xls, or .csv'}), 400
    
    try:
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        if file_ext == 'csv':
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Clean column names - remove whitespace and convert to lowercase
        df.columns = df.columns.str.strip().str.lower()
        
        # Flexible column mapping - find columns by keywords
        column_mapping = {}
        
        # Map Name column
        name_keywords = ['name']
        for col in df.columns:
            if any(keyword in col for keyword in name_keywords):
                column_mapping['name'] = col
                break
        
        # Map Email column
        email_keywords = ['email']
        for col in df.columns:
            if any(keyword in col for keyword in email_keywords):
                column_mapping['email'] = col
                break
        
        # Map Phone column
        phone_keywords = ['phone']
        for col in df.columns:
            if any(keyword in col for keyword in phone_keywords):
                column_mapping['phone'] = col
                break
        
        # Map Membership Duration column
        membership_keywords = ['membership', 'duration', 'plan']
        for col in df.columns:
            if any(keyword in col for keyword in membership_keywords):
                column_mapping['membership_duration'] = col
                break
        
        # Check if all required columns were found
        required_fields = ['name', 'email', 'phone', 'membership_duration']
        missing_fields = [field for field in required_fields if field not in column_mapping]
        
        if missing_fields:
            return jsonify({
                'success': False, 
                'message': f'Could not find columns for: {", ".join(missing_fields)}. Found columns: {", ".join(df.columns.tolist())}. Make sure your file has columns containing these keywords: name, email, phone, membership/duration.'
            }), 400
        
        success_count = 0
        error_count = 0
        errors = []
        
        current_date = datetime.now()
        
        for index, row in df.iterrows():
            try:
                # Extract data using mapped columns
                name_val = row[column_mapping['name']]
                email_val = row[column_mapping['email']]
                phone_val = row[column_mapping['phone']]
                membership_val = row[column_mapping['membership_duration']]
                
                # Skip rows with missing essential data
                if pd.isna(name_val) or pd.isna(email_val):
                    continue
                
                name = str(name_val).strip()
                email = str(email_val).strip()
                phone = str(phone_val).strip() if not pd.isna(phone_val) else ''
                membership_duration = str(membership_val).strip()
                
                # Normalize membership duration
                membership_duration = membership_duration.replace('months', 'Months').replace('month', 'Month')
                membership_duration = membership_duration.replace('years', 'Year').replace('year', 'Year')
                membership_duration = ' '.join(membership_duration.split())
                
                # Try to match with valid durations
                valid_durations = {
                    "1 Month": ["1 month", "1month", "1 months"],
                    "3 Months": ["3 months", "3months", "3 month"],
                    "6 Months": ["6 months", "6months", "6 month"],
                    "1 Year": ["1 year", "1year", "1 years", "12 months"]
                }
                
                matched_duration = None
                membership_duration_lower = membership_duration.lower()
                
                for standard, variations in valid_durations.items():
                    if membership_duration_lower in [v.lower() for v in variations] or membership_duration_lower == standard.lower():
                        matched_duration = standard
                        break
                
                if not matched_duration:
                    errors.append(f"Row {index + 2}: Invalid membership duration '{membership_duration}'. Use: 1 Month, 3 Months, 6 Months, or 1 Year")
                    error_count += 1
                    continue
                
                membership_duration = matched_duration
                membership_expiry = calculate_membership_expiry(current_date, membership_duration)
                amount_paid = membership_pricing.get(membership_duration, 0)
                
                # Check if student already exists
                existing_student = mongo.db.students.find_one({"email": email})
                
                if existing_student:
                    # Update existing student
                    mongo.db.students.update_one(
                        {"email": email},
                        {
                            "$set": {
                                "name": name,
                                "phone": phone,
                                "membership_duration": membership_duration,
                                "membership_expiry": membership_expiry,
                                "updated_at": current_date
                            }
                        }
                    )
                    student_id = existing_student['_id']
                else:
                    # Insert new student
                    student_id = mongo.db.students.insert_one({
                        "name": name,
                        "email": email,
                        "phone": phone,
                        "membership_duration": membership_duration,
                        "membership_expiry": membership_expiry,
                        "created_at": current_date
                    }).inserted_id
                
                # Add fee record
                mongo.db.fees.insert_one({
                    "student_id": ObjectId(student_id),
                    "amount_paid": amount_paid,
                    "payment_date": current_date,
                    "membership_duration": membership_duration,
                    "membership_expiry": membership_expiry,
                    "status": "Paid"
                })
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {index + 2}: {str(e)}")
        
        message = f"Successfully imported {success_count} students."
        if error_count > 0:
            message += f" {error_count} errors occurred."
        
        return jsonify({
            'success': True,
            'message': message,
            'details': {
                'success_count': success_count,
                'error_count': error_count,
                'errors': errors[:10]
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error processing file: {str(e)}'
        }), 500

@app.route('/students/download-template')
@login_required
def download_template():
    """Generate and download Excel template for student import"""
    try:
        # Create sample data
        template_data = {
            'Name': ['John Doe', 'Jane Smith'],
            'Email': ['john@example.com', 'jane@example.com'],
            'Phone': ['1234567890', '0987654321'],
            'Membership_Duration': ['3 Months', '1 Year']
        }
        
        df = pd.DataFrame(template_data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Students')
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='student_import_template.xlsx'
        )
    except Exception as e:
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('students'))

# ============================================================================
# ATTENDANCE ROUTES
# ============================================================================

@app.route("/fetch_attendance", methods=["GET"])
@login_required
def fetch_attendance():
    mark_attendance()
    return jsonify({"message": "Attendance marked successfully"}), 200

@app.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    if request.method == 'POST':
        student_id = request.form['student_id']
        date = request.form['date']
        status = request.form['status']
        
        mongo.db.attendance.insert_one({
            "student_id": student_id,
            "date": datetime.strptime(date, '%Y-%m-%d'),
            "status": status
        })
        flash("Attendance marked successfully!", "success")
        return redirect(url_for('attendance'))
    
    students = mongo.db.students.find()
    return render_template('attendance.html', students=students)


# ============================================================================
# FEES ROUTES
# ============================================================================

@app.route('/fees', methods=['GET', 'POST'])
@login_required
def fees():
    students = list(mongo.db.students.find())

    # Fetch fee records with proper formatting
    fee_records = list(mongo.db.fees.aggregate([
        {
            "$lookup": {
                "from": "students",
                "localField": "student_id",
                "foreignField": "_id",
                "as": "student"
            }
        },
        {"$unwind": "$student"},
        {
            "$project": {
                "student_name": "$student.name",
                "amount_paid": 1,
                "payment_date": 1,
                "membership_duration": 1,
                "membership_expiry": 1,
                "status": 1,
                "month": {"$month": "$payment_date"},
                "year": {"$year": "$payment_date"}
            }
        },
        {"$sort": {"payment_date": -1}}
    ]))

    # Group fees by month with proper date formatting
    fees_by_month = defaultdict(list)
    for record in fee_records:
        # Format dates properly - remove timestamps
        if isinstance(record.get('payment_date'), datetime):
            record['payment_date_formatted'] = record['payment_date'].strftime('%Y-%m-%d')
        else:
            record['payment_date_formatted'] = str(record.get('payment_date', 'N/A'))
            
        if isinstance(record.get('membership_expiry'), datetime):
            record['membership_expiry_formatted'] = record['membership_expiry'].strftime('%Y-%m-%d')
        else:
            record['membership_expiry_formatted'] = str(record.get('membership_expiry', 'N/A'))
        
        month_year = f"{record['year']}-{record['month']:02d}"
        fees_by_month[month_year].append(record)

    if request.method == 'POST':
        student_id = request.form['student_id']
        amount_paid = int(request.form['amount_paid'])
        payment_date_str = request.form['payment_date']
        membership_duration = request.form['membership_duration']
        status = request.form['status']

        payment_date_obj = datetime.strptime(payment_date_str, '%Y-%m-%d')
        
        # Calculate membership expiry
        membership_expiry = calculate_membership_expiry(payment_date_obj, membership_duration)

        # Insert fee record
        mongo.db.fees.insert_one({
            'student_id': ObjectId(student_id),
            'amount_paid': amount_paid,
            'payment_date': payment_date_obj,
            'membership_duration': membership_duration,
            'membership_expiry': membership_expiry,
            'status': status
        })
        
        # Update student's membership information automatically
        mongo.db.students.update_one(
            {"_id": ObjectId(student_id)},
            {
                "$set": {
                    "membership_duration": membership_duration,
                    "membership_expiry": membership_expiry
                }
            }
        )

        flash('Fee record added successfully! Student membership updated.', 'success')
        return redirect(url_for('fees'))

    return render_template('fees.html', fees_by_month=fees_by_month, students=students)

@app.route('/update-status', methods=['POST'])
@login_required
def update_status():
    data = request.get_json()
    fee_id = data.get('id')

    result = mongo.db.fees.update_one(
        {"_id": ObjectId(fee_id)},
        {"$set": {"status": "Paid"}}
    )

    return jsonify({"success": result.modified_count > 0})


# ============================================================================
# NOTIFICATION ROUTES
# ============================================================================

@app.route('/trigger-expiry-emails')
@login_required
def trigger_expiry_emails():
    today = datetime.now().date()

    expired_students = mongo.db.students.find({
        "membership_expiry": {
            "$lte": datetime(today.year, today.month, today.day),
            "$gt": datetime(today.year, today.month, today.day) - timedelta(days=1)
        }
    })

    count = 0
    for student in expired_students:
        if send_expiry_email(student):
            count += 1

    return f"✅ Sent {count} expiry reminder(s)."

@app.route('/send_notification', methods=['GET', 'POST'])
@login_required
def send_notification():
    if request.method == 'POST':
        subject = request.form['subject']
        message = request.form['message']
        only_expired = 'only_expired' in request.form

        today = datetime.now()

        if only_expired:
            students = mongo.db.students.find({
                "membership_expiry": {"$lt": today}
            })
        else:
            students = mongo.db.students.find()

        count = 0
        for student in students:
            if student.get('email'):
                try:
                    msg = Message(
                        subject=subject,
                        recipients=[student['email']],
                        body=f"Hi {student['name']},\n\n{message}\n\n- Geetanjali Yoga & Fitness Zone"
                    )
                    mail.send(msg)
                    count += 1
                except Exception as e:
                    print(f"Failed to send email to {student['email']}: {e}")

        flash(f"Notification sent to {count} students successfully!", "success")
        return redirect(url_for('send_notification'))

    return render_template('send_notification.html')

@app.route('/test_mail')
@login_required
def test_mail():
    try:
        msg = Message("Test Email",
                      recipients=["fitnessgeeta@gmail.com"],
                      body="This is a test email from Flask.")
        mail.send(msg)
        return "Email sent successfully!"
    except Exception as e:
        return f"Error sending email: {str(e)}"


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)