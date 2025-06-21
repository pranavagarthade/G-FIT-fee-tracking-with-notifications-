from flask import Flask, render_template, redirect, url_for, request, flash
from flask_pymongo import PyMongo
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from collections import defaultdict
from bson import ObjectId  
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import os
from dotenv import load_dotenv
from flask_mail import Mail, Message
from flask_apscheduler import APScheduler
import requests
import json
from flask import Flask, jsonify
from pymongo import MongoClient



app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MongoDB Setup
client = MongoClient("mongodb://localhost:27017/")
db = client["fitness_app"]
attendance_collection = db["attendance"]

# Zoom API Credentials
ZOOM_API_KEY = "dbwb3gMIRdGZ8AuZYBGCw"
ZOOM_API_SECRET = "5CcKa3lpnHS8aypS5xLuaiQ8wMEV5dLr"
MEETING_ID = "4945909109"

# Function to get participants from Zoom API
def get_zoom_participants(meeting_id):
    url = f"https://api.zoom.us/v2/report/meetings/4945909109/participants"
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
    

# Function to mark attendance
def mark_attendance():
    participants = get_zoom_participants(MEETING_ID)
    date_today = datetime.now().strftime("%Y-%m-%d")

    for participant in participants:
        student_name = participant.get("name")
        student_email = participant.get("user_email")

        if student_email:  # Only consider users with valid emails
            attendance_data = {
                "date": date_today,
                "batch": "5:00 to 6:00 AM",  # Adjust based on meeting timing
                "student_name": student_name,
                "email": student_email,
                "status": "Present",
            }
            attendance_collection.insert_one(attendance_data)
            print(f"Marked present: {student_name} ({student_email})")

@app.route("/fetch_attendance", methods=["GET"])
def fetch_attendance():
    mark_attendance()
    return jsonify({"message": "Attendance marked successfully"}), 200



app.config["MONGO_URI"] = "mongodb://localhost:27017/fitness_db"
mongo = PyMongo(app)


# scheduler = APScheduler()


from flask_mail import Mail, Message

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'fitnessgeeta@gmail.com'
app.config['MAIL_PASSWORD'] = 'txdjuwefdxjkrpng'  # remove all spaces here
app.config['MAIL_DEFAULT_SENDER'] = 'fitnessgeeta@gmail.com'


mail = Mail(app)



@app.route('/notify_student/<student_id>', methods=['POST'])
# @login_required
def notify_student(student_id):
    student = mongo.db.students.find_one({"_id": ObjectId(student_id)})

    if not student or not student.get("email"):
        flash("Student not found or email missing.", "error")
        return redirect(url_for('students'))

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
        flash(f"Notification sent to {student['name']}!", "success")

    except Exception as e:
        print("Email error:", e)
        flash("Failed to send email.", "error")

    return redirect(url_for('students'))


@app.route('/trigger-expiry-emails')
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
        send_expiry_email(student)
        count += 1

    return f"✅ Sent {count} expiry reminder(s)."

class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

@scheduler.task('cron', id='daily_expiry_email_job', hour=7)
def daily_expiry_email_job():
    with app.app_context():
        trigger_expiry_emails()
        
@app.route('/test_mail')
def test_mail():
    msg = Message("Test Email",
                  recipients=["your_email@gmail.com"],
                  body="This is a test email from Flask.")
    mail.send(msg)
    return "Email sent"





# def send_email_notification(subject, recipients, body):
#     msg = Message(subject, recipients=recipients)
#     msg.body = body
#     mail.send(msg)


# load_dotenv()


ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('You must log in first.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True  # This creates the session
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

@app.route('/')
def home():
    
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


membership_pricing = {
    "1 month": 1000, 
    "3 months": 2500,
    "6 months": 4500,
    "1 year": 8500
}


def calculate_membership_expiry(payment_date, membership_duration):
    if membership_duration == '1 month':
        return payment_date + relativedelta(months=1)
    elif membership_duration == '3 months':
        return payment_date + relativedelta(months=3)
    elif membership_duration == '6 months':
        return payment_date + relativedelta(months=6)
    elif membership_duration == '1 year':
        return payment_date + relativedelta(years=1)
    return None

# Route for Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    # Fetch statistics for dashboard
    print(session)
    total_students = mongo.db.students.count_documents({})
    expired_memberships = mongo.db.students.count_documents({"membership_expiry": {"$lt": datetime.now()}})
    pending_fees = mongo.db.fees.count_documents({"status": "Pending"})
    
    return render_template('dashboard.html', total_students=total_students,
                           expired_memberships=expired_memberships, pending_fees=pending_fees)



@app.route('/students', methods=['GET'])
def students():
    students = list(mongo.db.students.find())  # Convert Cursor to list
    return render_template('students.html', students=students, current_time=datetime.now())



@app.route('/students/add', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
       
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        membership_duration = request.form['membership_duration']
        fee_status = request.form['fee_status']  

        
        current_date = datetime.now()
        membership_expiry = calculate_membership_expiry(current_date, membership_duration)
        
        
        amount_paid = membership_pricing.get(membership_duration, 0)  
        payment_date = datetime.now().strftime('%Y-%m-%d')  

       
        student_id = mongo.db.students.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "membership_duration": membership_duration,
            "membership_expiry": membership_expiry  
        }).inserted_id  

        
        mongo.db.fees.insert_one({
            "student_id": ObjectId(student_id),
            "amount_paid": amount_paid,
            "payment_date": datetime.strptime(payment_date, '%Y-%m-%d'),
            "membership_duration": membership_duration,
            "membership_expiry": membership_expiry,
            "status": fee_status  
        })

        flash("Student and fee record added successfully!", "success")
        return redirect(url_for('students'))

    return render_template('add_student.html')


@app.route('/students/edit/<student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    student = mongo.db.students.find_one({"_id": ObjectId(student_id)})
    
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for('students'))
    
    if request.method == 'POST':
    
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        membership_duration = request.form['membership_duration']

       
        payment_date = datetime.now()
        membership_expiry = calculate_membership_expiry(payment_date, membership_duration)

        
        mongo.db.students.update_one(
            {"_id": ObjectId(student_id)},
            {
                "$set": {
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "membership_duration": membership_duration,
                    "membership_expiry": membership_expiry
                }
            }
        )

      
        mongo.db.fees.update_one(
            {"student_id": ObjectId(student_id)},
            {"$set": {"membership_duration": membership_duration}}
        )

        flash("Student updated successfully!", "success")
        return redirect(url_for('students'))

    return render_template('edit_student.html', student=student)


@app.route('/attendance', methods=['GET', 'POST'])
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


@app.route('/fees', methods=['GET', 'POST'])
def fees():
    students = list(mongo.db.students.find())  # Fetch students first

    # Define fee_records and fees_by_month early
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

    fees_by_month = defaultdict(list)
    for record in fee_records:
        month_year = f"{record['month']:02d}-{record['year']}"
        fees_by_month[month_year].append(record)

    if request.method == 'POST':
        student_id = request.form['student_id']
        amount_paid = request.form['amount_paid']
        payment_date = request.form['payment_date']
        membership_duration = request.form['membership_duration']
        status = request.form['status']

        payment_date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
        current_month = payment_date_obj.month
        current_year = payment_date_obj.year

        # Check if fee already exists for this student in the same month and year
        existing_fee = mongo.db.fees.find_one({
            "student_id": ObjectId(student_id),
            "$expr": {
                "$and": [
                    {"$eq": [{"$month": "$payment_date"}, current_month]},
                    {"$eq": [{"$year": "$payment_date"}, current_year]}
                ]
            }
        })

        if existing_fee:
            return render_template(
                'fees.html',
                fees_by_month=fees_by_month,
                students=students,
                show_popup=True
            )

        membership_expiry = calculate_membership_expiry(payment_date_obj, membership_duration)

        mongo.db.fees.insert_one({
            'student_id': ObjectId(student_id),
            'amount_paid': int(amount_paid),
            'payment_date': payment_date_obj,
            'membership_duration': membership_duration,
            'membership_expiry': membership_expiry,
            'status': status
        })

        flash('Fee record added successfully!', 'success')
        return redirect(url_for('fees'))

    return render_template('fees.html', fees_by_month=fees_by_month, students=students)

@app.route('/update-status', methods=['POST'])
def update_status():
    data = request.get_json()
    fee_id = data.get('id')

    result = mongo.db.fees.update_one(
        {"_id": ObjectId(fee_id)},
        {"$set": {"status": "Paid"}}
    )

    return jsonify({"success": result.modified_count > 0})




    # # 📊 Aggregation for fee records with student info
    # fee_records = list(mongo.db.fees.aggregate([
    #     {
    #         "$lookup": {
    #             "from": "students",
    #             "localField": "student_id",
    #             "foreignField": "_id",
    #             "as": "student"
    #         }
    #     },
    #     {
    #         "$unwind": "$student"
    #     },
    #     {
    #         "$project": {
    #             "student_name": "$student.name",
    #             "amount_paid": 1,
    #             "payment_date": 1,
    #             "membership_duration": 1,
    #             "membership_expiry": 1,
    #             "status": 1,
    #             "month": {"$month": "$payment_date"},
    #             "year": {"$year": "$payment_date"}
    #         }
    #     },
    #     {
    #         "$sort": {"payment_date": -1}
    #     }
    # ]))

    # # 📅 Group by month-year for display
    # fees_by_month = defaultdict(list)
    # for record in fee_records:
    #     month_year = f"{record['month']:02d}-{record['year']}"
    #     fees_by_month[month_year].append(record)

    # students = list(mongo.db.students.find())
    # return render_template('fees.html', fees_by_month=fees_by_month, students=students)





# def send_email_notification(subject, recipients, body):
#     msg = Message(subject, recipients=recipients)
#     msg.body = body
#     mail.send(msg)


# def check_membership_expiry():
#     current_date = datetime.now()
#     expiry_threshold = current_date + timedelta(days=2)
    
#     expiring_members = mongo.db.students.find({"membership_expiry": {"$lt": expiry_threshold, "$gte": current_date}})
    
#     for member in expiring_members:
#         subject = "Membership Expiry Reminder"
#         recipients = [member['email']]
#         message = f"Dear {member['name']}, your membership is expiring on {member['membership_expiry'].date()}. Please renew your membership."
#         send_email_notification(subject, recipients, message)


# scheduler.add_job(id='check_membership_expiry', func=check_membership_expiry, trigger='interval', days=1)
# scheduler.start()

def check_membership_expiry():
    current_date = datetime.now()
    expiry_threshold = current_date + timedelta(days=2)
    
    # Notify expiring soon
    expiring_members = mongo.db.students.find({
        "membership_expiry": {"$lt": expiry_threshold, "$gte": current_date}
    })

    for member in expiring_members:
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
        send_email_notification(
            "Membership Expired",
            [member['email']],
            f"Dear {member['name']}, your membership expired on {member['membership_expiry'].date()}. Please renew to continue attending classes."
        )



@app.route('/send_notification', methods=['GET', 'POST'])
# @login_required
# @app.route('/send-notification', methods=['GET', 'POST'])
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

        for student in students:
            if student.get('email'):
                msg = Message(
                    subject=subject,
                    recipients=[student['email']],
                    body=f"Hi {student['name']},\n\n{message}\n\n- Geetanjali Yoga & Fitness Zone"
                )
                mail.send(msg)

        flash("Notification sent successfully!", "success")
        return redirect(url_for('send_notification'))

    return render_template('send_notification.html')


@app.route('/students/delete/<student_id>', methods=['GET', 'POST'])
def delete_student(student_id):
    mongo.db.students.delete_one({"_id": ObjectId(student_id)})
    flash("Student deleted successfully!", "success")
    return redirect(url_for('students'))

if __name__ == '__main__':
    app.run(debug=True)

