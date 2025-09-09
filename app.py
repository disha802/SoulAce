from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import json
import os
from datetime import datetime
import csv
from pymongo import MongoClient
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import io
import sentiment_analysis as sa
from chatbot import EmotionalChatbot

# --- Load environment variables ---
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# --- Connect to MongoDB ---
client = MongoClient(MONGO_URI)
db = client["soulace"]

# Collections based on your schema
users_col = db["users"]
appointments_col = db["appointments"]
counselors_col = db["counselors"]
moodtracking_col = db["moodtracking"]
journals_col = db["journals"]
resources_col = db["resources"]
peersupportposts_col = db["peersupportposts"]

print("✅ Connected to MongoDB:", client.list_database_names())

# --- Flask setup ---
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secretkey123")

# --- Helper Functions ---
def get_next_id(collection, id_field):
    """Generate next sequential ID for a collection"""
    last_doc = collection.find_one(sort=[(id_field, -1)])
    if last_doc and id_field in last_doc:
        return int(last_doc[id_field]) + 1
    return 1

def create_default_admin():
    """Create default admin user if doesn't exist"""
    admin_exists = users_col.find_one({"role": "Admin"})
    if not admin_exists:
        admin_user = {
            "user_id": get_next_id(users_col, "user_id"),
            "username": "admin",
            "password_hash": generate_password_hash("adminpass"),
            "role": "Admin",
            "date_joined": datetime.now()
        }
        users_col.insert_one(admin_user)
        print("✅ Default admin user created")

def seed_sample_data():
    """Add sample counselors and resources if collections are empty"""
    # Sample Counselors
    if counselors_col.count_documents({}) == 0:
        sample_counselors = [
            {
                "counselor_id": 1,
                "name": "Dr. Sarah Johnson",
                "specialization": "Anxiety & Depression",
                "contact_info": "sarah.johnson@soulace.com"
            },
            {
                "counselor_id": 2,
                "name": "Dr. Michael Chen",
                "specialization": "Trauma Counseling",
                "contact_info": "michael.chen@soulace.com"
            },
            {
                "counselor_id": 3,
                "name": "Dr. Emily Rodriguez",
                "specialization": "Family Therapy",
                "contact_info": "emily.rodriguez@soulace.com"
            }
        ]
        counselors_col.insert_many(sample_counselors)
        print("✅ Sample counselors added")

    # Sample Resources
    if resources_col.count_documents({}) == 0:
        sample_resources = [
            {
                "resource_id": 1,
                "title": "Managing Anxiety: A Complete Guide",
                "type": "Guide",
                "language": "English",
                "url": "https://example.com/anxiety-guide"
            },
            {
                "resource_id": 2,
                "title": "Meditation for Beginners",
                "type": "Audio",
                "language": "English",
                "url": "https://example.com/meditation-audio"
            },
            {
                "resource_id": 3,
                "title": "Stress Relief Techniques",
                "type": "Video",
                "language": "English",
                "url": "https://example.com/stress-video"
            }
        ]
        resources_col.insert_many(sample_resources)
        print("✅ Sample resources added")

# Initialize default data
create_default_admin()
seed_sample_data()

# One-time update for existing users to add disclaimer fields
def update_existing_users_disclaimer():
    """Add disclaimer fields to existing users who don't have them"""
    result = users_col.update_many(
        {"disclaimer_accepted": {"$exists": False}},
        {"$set": {"disclaimer_accepted": False, "disclaimer_accepted_at": None}}
    )
    if result.modified_count > 0:
        print(f"✅ Updated {result.modified_count} existing users with disclaimer fields")

# Run the update
update_existing_users_disclaimer()

# --- Routes ---
@app.route("/")
def home():
    return render_template("welcome.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = users_col.find_one({"username": username})
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["user_id"]
            session["username"] = username
            session["role"] = user["role"]
            session["disclaimer_accepted"] = user.get("disclaimer_accepted", False)
            
            if user["role"] == "Admin":
                return redirect(url_for("admin_dashboard"))
            
            # Check if user needs to see disclaimer
            if not user.get("disclaimer_accepted", False):
                return redirect(url_for("disclaimer"))
            
            return redirect(url_for("dashboard"))
        else:
            flash("Incorrect username or password", "error")
    return render_template("login.html")

@app.route("/disclaimer")
def disclaimer():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # Check if user already accepted disclaimer
    user = users_col.find_one({"user_id": session["user_id"]})
    if user and user.get("disclaimer_accepted", False):
        return redirect(url_for("dashboard"))
    
    return render_template("disclaimer.html", username=session["username"])

@app.route("/accept_disclaimer", methods=["POST"])
def accept_disclaimer():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    if data.get("accepted"):
        # Update user record
        users_col.update_one(
            {"user_id": session["user_id"]},
            {
                "$set": {
                    "disclaimer_accepted": True,
                    "disclaimer_accepted_at": datetime.now()
                }
            }
        )
        
        # Update session
        session["disclaimer_accepted"] = True
        
        return jsonify({"success": True})
    
    return jsonify({"error": "Disclaimer not accepted"}), 400

# Middleware to check disclaimer acceptance
def require_disclaimer_acceptance():
    """Decorator to ensure user has accepted disclaimer before accessing protected routes"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            
            # Skip disclaimer check for admin users
            if session.get("role") == "Admin":
                return f(*args, **kwargs)
            
            # Check if disclaimer was accepted
            if not session.get("disclaimer_accepted", False):
                # Double-check with database
                user = users_col.find_one({"user_id": session["user_id"]})
                if not user or not user.get("disclaimer_accepted", False):
                    return redirect(url_for("disclaimer"))
                else:
                    # Update session if database shows acceptance
                    session["disclaimer_accepted"] = True
            
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        # Check if user already exists
        if users_col.find_one({"username": username}):
            flash("User already exists", "error")
        else:
            new_user = {
                "user_id": get_next_id(users_col, "user_id"),
                "username": username,
                "password_hash": generate_password_hash(password),
                "role": "User",
                "date_joined": datetime.now(),
                "disclaimer_accepted": False,  # NEW: Track disclaimer acceptance
                "disclaimer_accepted_at": None  # NEW: Track when it was accepted
            }
            users_col.insert_one(new_user)
            
            # Set session data
            session["user_id"] = new_user["user_id"]
            session["username"] = username
            session["role"] = "User"
            session["disclaimer_accepted"] = False
            
            flash("Registration successful!", "success")
            return redirect(url_for("disclaimer"))  # NEW: Redirect to disclaimer page
    return render_template("register.html")

@app.route("/dashboard")
@require_disclaimer_acceptance()
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", username=session["username"])

# --- Journal Routes ---
# @app.route("/journal")
# def journal():
#     if "user_id" not in session:
#         flash("Please login to access journals", "warning")
#         return redirect(url_for("login"))
#     return render_template("journal.html", username=session["username"])


@app.route("/journal", methods=["GET", "POST"])
@require_disclaimer_acceptance() 
def journal():
    if "user_id" not in session:
        return redirect("/login")

    journaling_prompt = None

    # ✅ Get latest mood of the user
    last_mood = moodtracking_col.find_one(
        {"user_id": session["user_id"]},
        sort=[("datetime", -1)]
    )

    if last_mood:
        mood = last_mood["mood"]

        if mood in ["Sad", "Frustrated", "Angry", "Crying"]:
            journaling_prompt = (
                "I'm sorry you're feeling this way. "
                "What do you think was the most saddening? "
                "Or among all the sad things, what's one thing that made you smile?"
            )
        elif mood in ["Very Happy", "Happy", "Feeling Blessed"]:
            journaling_prompt = (
                "That's wonderful! What made you feel this way today? "
                "Would you like to write it down so you can revisit it later?"
            )
        elif mood == "Mind Blown":
            journaling_prompt = (
                "Wow, sounds intense! What surprised or amazed you the most?"
            )

    # ✅ Render journal template with prompt
    return render_template("journal.html", journaling_prompt=journaling_prompt, username = session["username"])


@app.route("/add_journal", methods=["POST"])
def add_journal():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    
    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400

    entry = {
        "journal_id": get_next_id(journals_col, "journal_id"),
        "user_id": session["user_id"],
        "title": title,
        "entry": content,
        "datetime": datetime.now(),
        "is_edited": False,
        "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
        "time": data.get("time", datetime.now().strftime("%H:%M:%S"))
    }
    
    try:
        result = journals_col.insert_one(entry)
        print(f"✅ Inserted journal with ID: {entry['journal_id']}")
        return jsonify({"message": "Journal added successfully", "id": entry["journal_id"]}), 201
    except Exception as e:
        print(f"❌ Error inserting journal: {e}")
        return jsonify({"error": "Failed to save journal"}), 500

# Initialize chatbot (add this after your MongoDB setup)
try:
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        chatbot = EmotionalChatbot(api_key)
        print("✅ Chatbot initialized successfully")
    else:
        chatbot = None
        print("⚠️ GROQ_API_KEY not found - chatbot will not work")
except Exception as e:
    chatbot = None
    print(f"❌ Failed to initialize chatbot: {e}")

# --- Chatbot Routes ---
@app.route("/chatbot")
@require_disclaimer_acceptance() 
def chatbot_page():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("chatbot.html", username=session["username"])

@app.route("/chat", methods=["POST"])
def chat():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    if not chatbot:
        return jsonify({"response": "I'm sorry, the AI support is temporarily unavailable. Please try again later or contact our support team."}), 500
    
    data = request.get_json()
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"response": "I'm here to listen. Please share what's on your mind."}), 400
    
    try:
        response = chatbot.chat(message)
        return jsonify({"response": response})
    except Exception as e:
        print(f"Chatbot error: {e}")
        return jsonify({"response": "I'm here to support you. Could you tell me more about how you're feeling right now?"}), 500

@app.route("/get_journals/<username>", methods=["GET"])
def get_journals(username):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    user_entries = list(journals_col.find({"user_id": session["user_id"]}).sort("journal_id", -1))
    for e in user_entries:
        e["_id"] = str(e["_id"])
        e["id"] = e["journal_id"]  # For frontend compatibility
        e["content"] = e["entry"]  # For frontend compatibility
    return jsonify(user_entries)

@app.route("/delete_journal/<int:entry_id>", methods=["DELETE"])
def delete_journal(entry_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    res = journals_col.delete_one({"journal_id": entry_id, "user_id": session["user_id"]})
    if res.deleted_count == 1:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "not found"}), 404
    

# --- Mood Tracking Routes ---
@app.route("/save_mood", methods=["POST"])
def save_mood():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    mood = data.get("mood")

    # ✅ Define valid moods
    valid_moods = [
        "Very Happy", "Feeling Blessed", "Happy", "Mind Blown",
        "Frustrated", "Sad", "Angry", "Crying"
    ]
    if mood not in valid_moods:
        return jsonify({"error": "Invalid mood value"}), 400

    # ✅ Insert into DB
    mood_entry = {
        "mood_id": get_next_id(moodtracking_col, "mood_id"),
        "user_id": session["user_id"],
        "datetime": datetime.now(),
        "mood": mood
    }

    journaling_prompt = None
    # 🎯 Suggest journaling prompts based on mood
    if mood in ["Sad", "Frustrated", "Angry", "Crying"]:
        journaling_prompt = (
            "I'm sorry you're feeling this way. "
            "What do you think was the most saddening? "
            "Or among all the sad things, what's one thing that made you smile?"
        )
    elif mood in ["Very Happy", "Happy", "Feeling Blessed"]:
        journaling_prompt = (
            "That's wonderful! What made you feel this way today? "
            "Would you like to write it down so you can revisit it later?"
        )
    elif mood == "Mind Blown":
        journaling_prompt = (
            "Wow, sounds intense! What surprised or amazed you the most?"
        )

    try:
        moodtracking_col.insert_one(mood_entry)
        return jsonify({
            "message": f"Mood set to {mood}!",
            "journaling_prompt": journaling_prompt
        })
    except Exception as e:
        return jsonify({"error": "Failed to save mood"}), 500


@app.route("/get_moods")
def get_moods():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    moods = list(moodtracking_col.find({"user_id": session["user_id"]}).sort("datetime", -1))
    for mood in moods:
        mood["_id"] = str(mood["_id"])
    return jsonify(moods)

@app.route("/download_moods", methods=["GET"])
def download_csv():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # Get user's mood data
    moods = list(moodtracking_col.find({"user_id": session["user_id"]}).sort("datetime", 1))
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Time", "Mood"])
    
    for mood in moods:
        dt = mood["datetime"]
        writer.writerow([dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S"), mood["mood"]])
    
    # Convert to BytesIO for file download
    output.seek(0)
    file_data = io.BytesIO()
    file_data.write(output.getvalue().encode('utf-8'))
    file_data.seek(0)
    
    return send_file(file_data, 
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=f'moods_{session["username"]}.csv')

@app.route("/download_chart")
def download_chart():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    file_path = sa.generate_user_chart(session["user_id"], moodtracking_col)
    return send_file(file_path, as_attachment=True)


# --- Appointments Routes ---
@app.route("/appointments")
def appointments():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # Get user's appointments
    user_appointments = list(appointments_col.find({"user_id": session["user_id"]}).sort("datetime", 1))
    
    # Get counselor info for each appointment
    for appointment in user_appointments:
        counselor = counselors_col.find_one({"counselor_id": appointment["counselor_id"]})
        appointment["counselor_name"] = counselor["name"] if counselor else "Unknown"
        appointment["_id"] = str(appointment["_id"])
    
    # Get all counselors for booking
    all_counselors = list(counselors_col.find({}))
    for counselor in all_counselors:
        counselor["_id"] = str(counselor["_id"])
    
    return render_template("appointments.html", 
                         appointments=user_appointments, 
                         counselors=all_counselors,
                         username=session["username"])

@app.route("/book_appointment", methods=["POST"])
def book_appointment():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    counselor_id = data.get("counselor_id")
    datetime_str = data.get("datetime")
    
    try:
        appointment_datetime = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), 400
    
    appointment = {
        "appointment_id": get_next_id(appointments_col, "appointment_id"),
        "user_id": session["user_id"],
        "counselor_id": int(counselor_id),
        "datetime": appointment_datetime,
        "status": "Scheduled"
    }
    
    try:
        appointments_col.insert_one(appointment)
        return jsonify({"message": "Appointment booked successfully!"})
    except Exception as e:
        return jsonify({"error": "Failed to book appointment"}), 500

# --- Resources Routes ---
@app.route("/resources")
def resources():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    all_resources = list(resources_col.find({}))
    for resource in all_resources:
        resource["_id"] = str(resource["_id"])
    
    return render_template("resources.html", 
                         resources=all_resources,
                         username=session["username"])

# --- Peer Support Routes ---
@app.route("/peer_support")
def peer_support():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    posts = list(peersupportposts_col.find({}).sort("datetime", -1))
    
    # Add username for non-anonymous posts
    for post in posts:
        if not post["is_anonymous"]:
            user = users_col.find_one({"user_id": post["user_id"]})
            post["username"] = user["username"] if user else "Unknown"
        else:
            post["username"] = "Anonymous"
        post["_id"] = str(post["_id"])
    
    return render_template("peer_support.html", 
                         posts=posts,
                         username=session["username"])

@app.route("/add_post", methods=["POST"])
def add_post():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    content = data.get("content", "").strip()
    is_anonymous = data.get("is_anonymous", False)
    
    if not content:
        return jsonify({"error": "Content is required"}), 400
    
    post = {
        "post_id": get_next_id(peersupportposts_col, "post_id"),
        "user_id": session["user_id"],
        "datetime": datetime.now(),
        "content": content,
        "is_anonymous": bool(is_anonymous)
    }
    
    try:
        peersupportposts_col.insert_one(post)
        return jsonify({"message": "Post added successfully!"})
    except Exception as e:
        return jsonify({"error": "Failed to add post"}), 500

# --- Admin Routes ---
@app.route("/admin")
def admin_dashboard():
    if "user_id" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
    
    # Get statistics
    stats = {
        "total_users": users_col.count_documents({"role": "User"}),
        "total_journals": journals_col.count_documents({}),
        "total_appointments": appointments_col.count_documents({}),
        "total_posts": peersupportposts_col.count_documents({})
    }
    
    return render_template("admin_dashboard.html", 
                         username=session["username"],
                         stats=stats)

# --- Debug Routes ---
@app.route("/debug/all_collections")
def debug_all_collections():
    if "user_id" not in session or session["role"] != "Admin":
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        collections_info = {}
        
        # Get info for each collection
        collections = {
            "users": users_col,
            "journals": journals_col,
            "moodtracking": moodtracking_col,
            "appointments": appointments_col,
            "counselors": counselors_col,
            "resources": resources_col,
            "peersupportposts": peersupportposts_col
        }
        
        for name, col in collections.items():
            count = col.count_documents({})
            sample_docs = list(col.find({}).limit(2))
            for doc in sample_docs:
                doc["_id"] = str(doc["_id"])
            
            collections_info[name] = {
                "count": count,
                "sample_documents": sample_docs
            }
        
        return jsonify({
            "status": "Connected to MongoDB",
            "database": "soulace",
            "collections": collections_info
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Logout ---
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)