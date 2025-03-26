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

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Setup MongoDB connection (Replace with your actual MongoDB URI)
app.config["MONGO_URI"] = "mongodb://localhost:27017/fitness_db"
mongo = PyMongo(app)

# Load environment variables from the .env file
load_dotenv()

# Hardcoded admin credentials (you can move these to environment variables)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

# Decorator for requiring login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('You must log in first.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Route for login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check credentials
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True  # This creates the session
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('login.html')

# Route for logging out
@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/')
def home():
    # Redirect to the login page if the user is not logged in
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

# Define membership pricing based on duration
membership_pricing = {
    "1 month": 1000,  # Example price
    "3 months": 2500,
    "6 months": 4500,
    "1 year": 8500
}

# Global function to calculate membership expiry
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
# Route for Dashboard (fixing duplicate route)
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


# Route for managing students
@app.route('/students', methods=['GET'])
def students():
    # Fetch all students
    students = mongo.db.students.find()
    return render_template('students.html', students=students)

# Route for adding a student
@app.route('/students/add', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        # Handle adding a student
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        membership_duration = request.form['membership_duration']
        fee_status = request.form['fee_status']  # Capture the fee status

        # Calculate membership expiry
        current_date = datetime.now()
        membership_expiry = calculate_membership_expiry(current_date, membership_duration)
        
        # Get the fee amount from the membership_pricing dictionary
        amount_paid = membership_pricing.get(membership_duration, 0)  # Default to 0 if not found
        payment_date = datetime.now().strftime('%Y-%m-%d')  # Use current date as the payment date

        # Insert student data into MongoDB
        student_id = mongo.db.students.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "membership_duration": membership_duration,
            "membership_expiry": membership_expiry  # Store expiry date
        }).inserted_id  # Capture the student ID for the fee entry

        # Insert fee data based on the added student
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

# Route for editing a student
@app.route('/students/edit/<student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    student = mongo.db.students.find_one({"_id": ObjectId(student_id)})
    
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for('students'))
    
    if request.method == 'POST':
        # Get form data
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        membership_duration = request.form['membership_duration']

        # Calculate new membership expiry date
        payment_date = datetime.now()
        membership_expiry = calculate_membership_expiry(payment_date, membership_duration)

        # Update student information in MongoDB
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

        # Update fee information if needed
        mongo.db.fees.update_one(
            {"student_id": ObjectId(student_id)},
            {"$set": {"membership_duration": membership_duration}}
        )

        flash("Student updated successfully!", "success")
        return redirect(url_for('students'))

    return render_template('edit_student.html', student=student)

# Route for marking attendance
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

# Route for managing fees
@app.route('/fees', methods=['GET', 'POST'])
def fees():
    if request.method == 'POST':
        # Handle the form submission to add new fee records
        student_id = request.form['student_id']
        amount_paid = request.form['amount_paid']
        payment_date = request.form['payment_date']
        membership_duration = request.form['membership_duration']
        status = request.form['status']

        # Calculate membership expiry based on payment date and membership duration
        payment_date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
        membership_expiry = calculate_membership_expiry(payment_date_obj, membership_duration)

        # Insert the fee record into the database
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

    # Retrieve the fee records and group by month and year
    fee_records = list(mongo.db.fees.aggregate([
        {
            "$lookup": {
                "from": "students",
                "localField": "student_id",
                "foreignField": "_id",
                "as": "student"
            }
        },
        {
            "$unwind": "$student"
        },
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
        {
            "$sort": {"payment_date": -1}  # Sort by latest payment date first
        }
    ]))

    # Organize the records by month and year
    fees_by_month = defaultdict(list)
    for record in fee_records:
        month_year = f"{record['month']:02d}-{record['year']}"  # Format as MM-YYYY
        fees_by_month[month_year].append(record)

    # Render the template with the grouped fees
    students = list(mongo.db.students.find())
    return render_template('fees.html', fees_by_month=fees_by_month, students=students)

# Route for sending notifications
@app.route('/send_notification', methods=['GET', 'POST'])
def send_notification():
    if request.method == 'POST':
        message = request.form['message']
        
        # Logic for sending notifications (e.g., via email or SMS)
        flash("Notifications sent successfully!", "success")
        return redirect(url_for('send_notification'))
    
    return render_template('send_notification.html')

# Route to delete a student
@app.route('/students/delete/<student_id>', methods=['GET', 'POST'])
def delete_student(student_id):
    mongo.db.students.delete_one({"_id": ObjectId(student_id)})
    flash("Student deleted successfully!", "success")
    return redirect(url_for('students'))

if __name__ == '__main__':
    app.run(debug=True)

