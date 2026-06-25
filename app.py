from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
from datetime import datetime
import requests
import json

app = Flask(__name__)
app.secret_key = "foodshare_secret_key"


# ==========================
# MySQL Connection Function
# ==========================

def get_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="mysql",          # Add your MySQL password if any
        database="food",
        cursorclass=pymysql.cursors.DictCursor
    )


# ==========================
# AI Priority Function (Gemini-Powered)
# ==========================

def get_ai_food_analysis(food_description, storage_condition, hours_since_prep):
    """
    Call the FastAPI Gemini endpoint to get AI-powered food analysis.
    Returns dict with tier, urgency_score, consumption_window_hours, handling_instructions, reasoning.
    Falls back to simple priority if API fails.
    """
    try:
        response = requests.post(
            "http://127.0.0.1:8000/api/analyze-food",
            json={
                "description": food_description,
                "storage_condition": storage_condition,
                "hours_since_prep": hours_since_prep
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get('data', {})
        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return None


def calculate_priority(condition, quantity, people_served):
    """Legacy fallback function if AI is unavailable"""
    score = 0

    if condition.lower() == "fresh":
        score += 50

    elif condition.lower() == "good":
        score += 30

    else:
        score += 10

    if float(quantity) > 20:
        score += 30

    elif float(quantity) > 10:
        score += 20

    if int(people_served) > 100:
        score += 20

    if score >= 80:
        return "HIGH"

    elif score >= 50:
        return "MEDIUM"

    return "LOW"


# ==========================
# Home Page
# ==========================

@app.route('/')
def home():
    return render_template('index.html')


# ==========================
# Register Page
# ==========================

@app.route('/register')
def register_page():
    return render_template('register.html')


# ==========================
# Login Page
# ==========================

@app.route('/login')
def login_page():
    return render_template('loginuser.html')

# ==========================
# REGISTER USER
# ==========================

@app.route('/register', methods=['POST'])
def register():

    name = request.form['name']
    email = request.form['email']
    phone = request.form['phone']
    organization = request.form['organization']
    address = request.form['address']
    city = request.form['city']
    password = request.form['password']
    user_type = request.form['userType']

    conn = get_connection()
    cursor = conn.cursor()

    # Check if email already exists
    cursor.execute(
        "SELECT * FROM users WHERE email=%s",
        (email,)
    )

    existing_user = cursor.fetchone()

    if existing_user:
        flash("Email already registered!")
        conn.close()
        return redirect('/register')

    # Insert new user
    cursor.execute("""
        INSERT INTO users
        (name,email,phone,organization,address,city,password,user_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        name,
        email,
        phone,
        organization,
        address,
        city,
        password,
        user_type
    ))

    conn.commit()
    conn.close()

    flash("Registration Successful!")

    return redirect('/login')


# ==========================
# LOGIN USER
# ==========================

@app.route('/login', methods=['POST'])
def login():

    email = request.form['email']
    password = request.form['password']
    user_type = request.form['userType']

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM users
        WHERE email=%s
        AND password=%s
        AND user_type=%s
    """, (
        email,
        password,
        user_type
    ))

    user = cursor.fetchone()

    conn.close()

    if not user:
        flash("Invalid Login Credentials")
        return redirect('/login')

    # Store session data
    session['user_id'] = user['id']
    session['name'] = user['name']
    session['user_type'] = user['user_type']
    session['organization'] = user['organization']

    # Redirect according to user_type
    if user['user_type'] == 'donor':
        return redirect('/donor_dashboard')

    elif user['user_type'] == 'ngo':
        return redirect('/ngo_dashboard')

    return redirect('/')


# ==========================
# ADMIN LOGIN
# ==========================

@app.route('/admin_login')
def admin_login():

    session['name'] = "Admin"
    session['user_type'] = "admin"

    return redirect('/admin')


# ==========================
# LOGOUT
# ==========================

@app.route('/logout')
def logout():

    session.clear()

    flash("Logged Out Successfully")

    return redirect('/')


# ==========================
# SESSION CHECK HELPERS
# ==========================

def donor_required():

    if 'user_id' not in session:
        return False

    if session.get('user_type') != 'donor':
        return False

    return True


def ngo_required():

    if 'user_id' not in session:
        return False

    if session.get('user_type') != 'ngo':
        return False

    return True

# ==========================
# DONATE FOOD PAGE
# ==========================

@app.route('/donor-food')
def donor_food_alias():
    return redirect('/donor_food')

@app.route('/donor_food')
def donor_food():

    if not donor_required():
        return redirect('/login')

    return render_template('donor_food.html')

# ==========================
# SAVE DONATION
# ==========================

@app.route('/donate', methods=['POST'])
def donate_food():

    if not donor_required():
        return redirect('/login')

    donor_id = session['user_id']
    food_type = request.form['food-type']
    food_name = request.form['food-name']
    quantity = request.form['quantity']
    people_served = request.form['people-served']
    expiry_date = request.form['expiry-date']
    expiry_time = request.form['expiry-time']
    food_condition = request.form['condition']
    location = request.form['location']
    city = request.form['city']
    contact = request.form['contact']
    details = request.form['details']
    preparation_date= request.form['prep-date']
    preparation_time= request.form['prep-time']
    odor_check = request.form['visual-check']
    storage= request.form['storage']

    # Calculate hours since preparation for AI analysis
    from datetime import datetime as dt
    try:
        prep_datetime = dt.strptime(f"{preparation_date} {preparation_time}", "%Y-%m-%d %H:%M")
        hours_since_prep = (dt.now() - prep_datetime).total_seconds() / 3600
    except:
        hours_since_prep = 0

    # Call Gemini AI for food analysis
    food_description = f"{food_type}: {food_name}. {details}"
    ai_analysis = get_ai_food_analysis(food_description, storage, hours_since_prep)
    
    # Use AI tier, fallback to legacy priority if AI unavailable
    if ai_analysis:
        ai_priority = ai_analysis.get('tier', 'Good')  # Best, Better, or Good
        urgency_score = ai_analysis.get('urgency_score', 5)
        consumption_hours = ai_analysis.get('consumption_window_hours', 12)
        handling_instructions = ai_analysis.get('handling_instructions', '')
        reasoning = ai_analysis.get('reasoning', '')
    else:
        fallback = calculate_priority(food_condition, quantity, people_served)
        ai_priority = fallback
        urgency_score = 10 if fallback == "HIGH" else (5 if fallback == "MEDIUM" else 1)
        consumption_hours = 4 if fallback == "HIGH" else (12 if fallback == "MEDIUM" else 24)
        handling_instructions = f"Fallback priority based on condition: {fallback}"
        reasoning = f"AI analysis unavailable, using legacy calculation"

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO donations(
            donor_id,
            food_type,
            food_name,
            quantity,
            people_served,
            expiry_date,
            expiry_time,
            food_condition,
            location,
            city,
            contact,
            details,
            ai_priority,
            preparation_date,
            preparation_time,
            odor_check,
            storage
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        donor_id,
        food_type,
        food_name,
        quantity,
        people_served,
        expiry_date,
        expiry_time,
        food_condition,
        location,
        city,
        contact,
        details,
        ai_priority,
        preparation_date,
        preparation_time,   
        odor_check,
        storage
    ))

    conn.commit()
    conn.close()

    flash(
        f"Food donated successfully! AI Priority: {ai_priority}"
    )

    return redirect('/my_donations')

# ==========================
# MY DONATIONS
# ==========================

@app.route('/my_donations')
def my_donations():

    if not donor_required():
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM donations
        WHERE donor_id=%s
        ORDER BY id DESC
    """, (session['user_id'],))

    donations = cursor.fetchall()

    conn.close()

    return render_template(
        'my_donations.html',
        donations=donations
    )

@app.route('/donor_dashboard')
def donor_dashboard():

    if not donor_required():
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) total
        FROM donations
        WHERE donor_id=%s
    """, (session['user_id'],))

    total_donations = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COALESCE(SUM(quantity),0) total_food
        FROM donations
        WHERE donor_id=%s
    """, (session['user_id'],))

    food_donated = cursor.fetchone()['total_food']

    cursor.execute("""
        SELECT COUNT(DISTINCT id) ngos_helped
        FROM donations
        WHERE donor_id=%s
        AND status='claimed'
    """, (session['user_id'],))

    ngos_helped = cursor.fetchone()['ngos_helped']

    conn.close()

    return render_template(
        'donor_dashboard.html',
        name=session['name'],
        organization=session['organization'],
        total_donations=total_donations,
        food_donated=food_donated,
        ngos_helped=ngos_helped
    )

# ==========================
# DONOR STATISTICS
# ==========================

@app.route('/donor_statistics')
def donor_statistics():

    if not donor_required():
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    # Total Donations
    cursor.execute("""
        SELECT COUNT(*) total
        FROM donations
        WHERE donor_id=%s
    """, (session['user_id'],))
    total_donations = cursor.fetchone()['total']

    # Total Food Donated
    cursor.execute("""
        SELECT COALESCE(SUM(quantity),0) total_food
        FROM donations
        WHERE donor_id=%s
    """, (session['user_id'],))
    total_food = cursor.fetchone()['total_food']

    # Claimed Donations
    cursor.execute("""
        SELECT COUNT(*) total
        FROM donations
        WHERE donor_id=%s
        AND status='claimed'
    """, (session['user_id'],))
    claimed = cursor.fetchone()['total']

    # Available Donations
    cursor.execute("""
        SELECT COUNT(*) total
        FROM donations
        WHERE donor_id=%s
        AND status='available'
    """, (session['user_id'],))
    available = cursor.fetchone()['total']

    # Food Type Breakdown
    cursor.execute("""
        SELECT
            food_type,
            COUNT(*) total,
            SUM(quantity) total_qty
        FROM donations
        WHERE donor_id=%s
        GROUP BY food_type
    """, (session['user_id'],))
    food_types = cursor.fetchall()

    # Priority Breakdown
    cursor.execute("""
        SELECT
            ai_priority,
            COUNT(*) total
        FROM donations
        WHERE donor_id=%s
        GROUP BY ai_priority
    """, (session['user_id'],))
    priorities = cursor.fetchall()

    # Total People Served
    cursor.execute("""
        SELECT COALESCE(SUM(people_served),0) total
        FROM donations
        WHERE donor_id=%s
    """, (session['user_id'],))
    people_served = cursor.fetchone()['total']

    conn.close()

    return render_template(
        'donor_statistics.html',
        name=session['name'],
        organization=session['organization'],
        total_donations=total_donations,
        total_food=total_food,
        claimed=claimed,
        available=available,
        food_types=food_types,
        priorities=priorities,
        people_served=people_served
    )

# ==========================
# AVAILABLE FOOD
# ==========================

@app.route('/available_food')
def available_food():

    if not ngo_required():
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            donations.*,
            users.organization
        FROM donations
        JOIN users
        ON donations.donor_id = users.id
        WHERE donations.status='available'
        ORDER BY donations.id DESC
    """)

    foods = cursor.fetchall()

    conn.close()

    return render_template(
        'availfood.html',
        foods=foods
    )

# ==========================
# CLAIM FOOD
# ==========================

@app.route('/claim', defaults={'food_id': None})
@app.route('/claim/<int:food_id>')
def claim_food(food_id):

    if food_id is None:
        flash("No food item selected for claim.")
        return redirect('/available_food')

    if not ngo_required():
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    # Add claim
    cursor.execute("""
        INSERT INTO claims(
            donation_id,
            ngo_id
        )
        VALUES(%s,%s)
    """, (
        food_id,
        session['user_id']
    ))

    # Update donation status
    cursor.execute("""
        UPDATE donations
        SET status='claimed'
        WHERE id=%s
    """, (food_id,))

    conn.commit()
    conn.close()

    flash("Food Claimed Successfully")

    return redirect('/available_food')

@app.route('/ngo_dashboard')
def ngo_dashboard():

    if not ngo_required():
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    # Total Claims
    cursor.execute("""
        SELECT COUNT(*) total
        FROM claims
        WHERE ngo_id=%s
    """, (session['user_id'],))

    total_claims = cursor.fetchone()['total']

    # Food Received
    cursor.execute("""
        SELECT COALESCE(SUM(d.quantity),0) total_food
        FROM donations d
        JOIN claims c
        ON d.id=c.donation_id
        WHERE c.ngo_id=%s
    """, (session['user_id'],))

    food_received = cursor.fetchone()['total_food']

    # People Helped
    cursor.execute("""
        SELECT COALESCE(SUM(d.people_served),0) total_people
        FROM donations d
        JOIN claims c
        ON d.id=c.donation_id
        WHERE c.ngo_id=%s
    """, (session['user_id'],))

    people_helped = cursor.fetchone()['total_people']

    conn.close()

    return render_template(
        'ngo_dashboard.html',
        name=session['name'],
        organization=session['organization'],
        total_claims=total_claims,
        food_received=food_received,
        people_helped=people_helped
    )


# ==========================
# NGO STATISTICS
# ==========================

@app.route('/ngo_statistics')
def ngo_statistics():

    if not ngo_required():
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    # Total Claims
    cursor.execute("""
        SELECT COUNT(*) total
        FROM claims
        WHERE ngo_id=%s
    """, (session['user_id'],))
    total_claims = cursor.fetchone()['total']

    # Food Received (sum of quantities for claimed donations)
    cursor.execute("""
        SELECT COALESCE(SUM(d.quantity),0) total_food
        FROM donations d
        JOIN claims c
        ON d.id=c.donation_id
        WHERE c.ngo_id=%s
    """, (session['user_id'],))
    food_received = cursor.fetchone()['total_food']

    # People Helped
    cursor.execute("""
        SELECT COALESCE(SUM(d.people_served),0) total_people
        FROM donations d
        JOIN claims c
        ON d.id=c.donation_id
        WHERE c.ngo_id=%s
    """, (session['user_id'],))
    people_helped = cursor.fetchone()['total_people']

    # Breakdown by food type (for this NGO's claims)
    cursor.execute("""
        SELECT
            d.food_type,
            COUNT(*) total,
            SUM(d.quantity) total_qty
        FROM claims c
        JOIN donations d
        ON c.donation_id=d.id
        WHERE c.ngo_id=%s
        GROUP BY d.food_type
    """, (session['user_id'],))
    food_types = cursor.fetchall()

    # Recent claims list
    cursor.execute("""
        SELECT
            c.id AS claim_id,
            d.food_name,
            d.food_type,
            d.quantity,
            d.people_served,
            u.organization AS donor_name,
            c.id
        FROM claims c
        JOIN donations d
        ON c.donation_id = d.id
        JOIN users u
        ON d.donor_id = u.id
        WHERE c.ngo_id=%s
        ORDER BY c.id DESC
        LIMIT 20
    """, (session['user_id'],))
    recent_claims = cursor.fetchall()

    conn.close()

    return render_template(
        'ngo_statistics.html',
        name=session['name'],
        organization=session['organization'],
        total_claims=total_claims,
        food_received=food_received,
        people_helped=people_helped,
        food_types=food_types,
        recent_claims=recent_claims
    )

# ==========================
# MY CLAIMS
# ==========================

@app.route('/my_claims')
def my_claims():

    if not ngo_required():
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            donations.*
        FROM donations
        JOIN claims
        ON donations.id = claims.donation_id
        WHERE claims.ngo_id=%s
        ORDER BY claims.id DESC
    """, (session['user_id'],))

    claims_data = cursor.fetchall()

    conn.close()

    return render_template(
        'my_claims.html',
        claims=claims_data
    )

# ==========================
# ADMIN DASHBOARD
# ==========================

@app.route('/admin')
def admin_dashboard():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) total_users
        FROM users
    """)
    total_users = cursor.fetchone()['total_users']

    cursor.execute("""
        SELECT COUNT(*) total_donations
        FROM donations
    """)
    total_donations = cursor.fetchone()['total_donations']

    cursor.execute("""
        SELECT COALESCE(SUM(quantity),0) total_food
        FROM donations
    """)
    total_food = cursor.fetchone()['total_food']

    cursor.execute("""
        SELECT COUNT(*) total_ngos
        FROM users
        WHERE user_type='ngo'
    """)
    total_ngos = cursor.fetchone()['total_ngos']

    cursor.execute("""
        SELECT COALESCE(SUM(people_served),0) total_people
        FROM donations
    """)
    total_people = cursor.fetchone()['total_people']

    cursor.execute("""
        SELECT COUNT(*) pending_claims
        FROM donations
        WHERE status='available'
    """)
    pending_claims = cursor.fetchone()['pending_claims']

    conn.close()

    return render_template(
        'admin.html',
        total_users=total_users,
        total_donations=total_donations,
        total_food=total_food,
        total_ngos=total_ngos,
        total_people=total_people,
        pending_claims=pending_claims
    )

# ==========================
# ALL USERS
# ==========================

@app.route('/all_users')
def all_users():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        ORDER BY id DESC
    """)

    users = cursor.fetchall()

    conn.close()

    return render_template(
        'all_users.html',
        users=users
    )

# ==========================
# DELETE USER
# ==========================

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM users
        WHERE id=%s
    """, (user_id,))

    conn.commit()
    conn.close()

    flash("User Deleted")

    return redirect('/all_users')

# ==========================
# REPORTS
# ==========================

@app.route('/reports')
def reports():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
        food_type,
        COUNT(*) total
        FROM donations
        GROUP BY food_type
    """)

    food_types = cursor.fetchall()

    conn.close()

    return render_template(
        'reports.html',
        food_types=food_types
    )

# ==========================
# DONATION HISTORY REPORT
# ==========================

@app.route('/donation_history')
def donation_history():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            d.id,
            d.food_name,
            d.food_type,
            d.quantity,
            d.people_served,
            d.status,
            u.organization
        FROM donations d
        JOIN users u
        ON d.donor_id = u.id
        ORDER BY d.id DESC
    """)

    donations = cursor.fetchall()

    conn.close()

    return render_template(
        'donation_history.html',
        donations=donations
    )

# ==========================
# CLAIM HISTORY
# ==========================

@app.route('/claim_history')
def claim_history():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            c.id,
            d.food_name,
            d.quantity,
            u.organization ngo_name
        FROM claims c
        JOIN donations d
        ON c.donation_id = d.id
        JOIN users u
        ON c.ngo_id = u.id
        ORDER BY c.id DESC
    """)

    claims = cursor.fetchall()

    conn.close()

    return render_template(
        'claim_history.html',
        claims=claims
    )

# ==========================
# SYSTEM STATISTICS
# ==========================

@app.route('/stats')
def stats():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) total FROM users")
    users = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) total FROM donations")
    donations = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COALESCE(SUM(quantity),0) total
        FROM donations
    """)
    food = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COALESCE(SUM(people_served),0) total
        FROM donations
    """)
    people = cursor.fetchone()['total']

    conn.close()

    return {
        "users": users,
        "donations": donations,
        "food": float(food),
        "people": int(people)
    }



if(__name__ == '__main__'):
    app.run(debug=True)