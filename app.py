from flask import Flask, render_template, redirect, url_for, request, flash
from flask_pymongo import PyMongo
from datetime import datetime
from dateutil.relativedelta import relativedelta
from bson import ObjectId  # Ensure this import is present for ObjectId

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Setup MongoDB connection (Replace with your actual MongoDB URI)
app.config["MONGO_URI"] = "mongodb://localhost:27017/fitness_db"
mongo = PyMongo(app)

# Route for Dashboard
@app.route('/')
def dashboard():
    # Fetch some statistics from MongoDB
    total_students = mongo.db.students.count_documents({})
    expired_memberships = mongo.db.students.count_documents({"membership_expiry": {"$lt": datetime.now()}})
    pending_fees = mongo.db.fees.count_documents({"status": "Pending"})
    
    return render_template('dashboard.html', total_students=total_students,
                           expired_memberships=expired_memberships, pending_fees=pending_fees)

# Route for managing students
@app.route('/students', methods=['GET', 'POST'])
def students():
    if request.method == 'POST':
        # Adding new student
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        membership_expiry = request.form['membership_expiry']
        
        # Insert the student information into the students collection
        student_id = mongo.db.students.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "membership_expiry": datetime.strptime(membership_expiry, '%Y-%m-%d')
        }).inserted_id
        
        # After adding the student, create a corresponding entry in the fees collection
        mongo.db.fees.insert_one({
            "student_id": ObjectId(student_id),  # Ensure student_id is stored as ObjectId
            "amount_paid": 0,  # Initially no payment
            "payment_date": None,  # No payment date initially
            "membership_duration": "1 month",  # Default duration, can be adjusted later
            "status": "Pending"  # Initial status is pending payment
        })
        
        flash("Student and initial fee record added successfully!", "success")
        return redirect(url_for('students'))
    
    # Fetch all students
    students = mongo.db.students.find()
    return render_template('students.html', students=students)

# Function to calculate membership expiry based on payment date and duration
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



# Route for adding/editing a student
@app.route('/students/add', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        # Handle adding or editing a student (simplified)
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        membership_expiry = request.form['membership_expiry']
        
        mongo.db.students.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "membership_expiry": datetime.strptime(membership_expiry, '%Y-%m-%d')
        })
        flash("Student added successfully!", "success")
        return redirect(url_for('students'))
    
    return render_template('add_student.html')

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
        # Capture form data
        student_id = request.form['student_id']
        amount_paid = request.form['amount_paid']
        payment_date = request.form['payment_date']
        membership_duration = request.form['membership_duration']
        status = request.form['status']

        # Convert the payment date to a datetime object
        payment_date_obj = datetime.strptime(payment_date, '%Y-%m-%d')

        # Calculate membership expiry based on duration
        membership_expiry = calculate_membership_expiry(payment_date_obj, membership_duration)

        # Insert fee record into the fees collection
        mongo.db.fees.insert_one({
            "student_id": ObjectId(student_id),
            "amount_paid": amount_paid,
            "payment_date": payment_date_obj,
            "membership_duration": membership_duration,
            "membership_expiry": membership_expiry,
            "status": status
        })

        flash("Fee record added successfully!", "success")
        return redirect(url_for('fees'))
    
      # Fetch students for the dropdown
    students = mongo.db.students.find() 

    # Fetch all fees and corresponding student names for display
    fees = mongo.db.fees.find()
    fee_list = []

    for fee in fees:
        student = mongo.db.students.find_one({"_id": ObjectId(fee['student_id'])})
        fee_data = {
            "student_name": student['name'] if student else "Unknown",
            "amount_paid": fee['amount_paid'],
            "payment_date": fee['payment_date'].strftime('%Y-%m-%d') if fee['payment_date'] else "N/A",
            "membership_duration": fee['membership_duration'],
            "membership_expiry": fee['membership_expiry'].strftime('%Y-%m-%d') if fee['membership_expiry'] else "N/A",
            "status": fee['status'],
            "_id": fee['_id']
        }
        fee_list.append(fee_data)

    return render_template('fees.html', fees=fee_list, students=students)
# Route for sending notifications to students
@app.route('/send_notification', methods=['GET', 'POST'])
def send_notification():
    if request.method == 'POST':
        message = request.form['message']
        
        # Logic for sending notifications (e.g., via email or SMS)
        # Placeholder for sending emails or SMS notifications
        
        flash("Notifications sent successfully!", "success")
        return redirect(url_for('send_notification'))
    
    return render_template('send_notification.html')

# Route to edit student (for simplicity, redirecting to same page in this demo)
@app.route('/students/edit/<student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    if request.method == 'POST':
        # Example of how you would handle editing a student
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        membership_expiry = request.form['membership_expiry']
        
        mongo.db.students.update_one(
            {"_id": student_id},
            {"$set": {
                "name": name,
                "email": email,
                "phone": phone,
                "membership_expiry": datetime.strptime(membership_expiry, '%Y-%m-%d')
            }}
        )
        flash("Student updated successfully!", "success")
        return redirect(url_for('students'))
    
    student = mongo.db.students.find_one({"_id": student_id})
    return render_template('edit_student.html', student=student)

# Route to delete student
@app.route('/students/delete/<student_id>', methods=['GET', 'POST'])
def delete_student(student_id):
    mongo.db.students.delete_one({"_id": student_id})
    flash("Student deleted successfully!", "success")
    return redirect(url_for('students'))

if __name__ == '__main__':
    app.run(debug=True)
