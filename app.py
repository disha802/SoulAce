from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import json
import os
from datetime import datetime
import csv
from pymongo import MongoClient
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from datetime import datetime
import io
import sentiment_analysis as sa
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

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
therapists_col = db['therapists']
slots_col = db['slots']        # timeslot documents
bookings_col = db['bookings']  # bookings
proctors_col = db['proctors']
slots_col = db['slots']
bookings_col = db['bookings']
crisis_col = db["crisis_logs"]
crisis_col = db["crisis"]

print("✅ Connected to MongoDB:", client.list_database_names())

# --- AI Moderation Setup ---
class AIModerator:
    def __init__(self):
        self.model_name = "unitary/toxic-bert"
        self.tokenizer = None
        self.model = None
        self.load_model()
        
    def load_model(self):
        """Load the AI model for content moderation"""
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            print("✅ AI Moderation model loaded successfully")
        except Exception as e:
            print(f"❌ Error loading AI model: {e}")
            self.model = None
            
    def moderate(self, text):
        """
        Analyze text for toxic content using AI model
        Returns: (is_toxic, confidence_score, categories)
        """
        if not self.model or not text or not isinstance(text, str):
            return False, 0.0, []
            
        try:
            # Tokenize input
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            
            # Get model prediction
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # Apply sigmoid to get probabilities
            probs = torch.sigmoid(outputs.logits).squeeze().tolist()
            
            # Define toxicity categories (based on model's training)
            categories = ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]
            
            # Check if any category exceeds threshold
            threshold = 0.7
            max_prob = max(probs) if isinstance(probs, list) else probs
            is_toxic = max_prob > threshold
            
            # Get the categories that exceeded threshold
            toxic_categories = []
            if isinstance(probs, list):
                for i, prob in enumerate(probs):
                    if prob > threshold and i < len(categories):
                        toxic_categories.append(categories[i])
            elif probs > threshold:
                toxic_categories = ["toxic"]
                
            return is_toxic, max_prob, toxic_categories
        except Exception as e:
            print(f"Error in AI moderation: {e}")
            return False, 0.0, []

# Initialize AI Moderator
ai_moderator = AIModerator()

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

def create_default_Admin():
    """Create default Admin user if doesn't exist"""
    Admin_exists = users_col.find_one({"role": "admin"})
    if not Admin_exists:
        Admin_user = {
            "user_id": get_next_id(users_col, "user_id"),
            "username": "Admin",
            "password_hash": generate_password_hash("adminpass"),
            "role": "admin",
            "date_joined": datetime.now()
        }
        users_col.insert_one(Admin_user)
        print("✅ Default Admin user created")

    
    # Create default studentvol user
    stuvol_exists = users_col.find_one({"username": "studentvol"})
    if not stuvol_exists:
        stuvol_user = {
            "user_id": get_next_id(users_col, "user_id"),
            "username": "studentvol",
            "password_hash": generate_password_hash("studentvol"),
            "role": "studentvol",
            "date_joined": datetime.now()
        }
        users_col.insert_one(stuvol_user)
        print("✅ Default studentvol user created (username: studentvol, password: studentvol)")

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

def check(content: str) -> dict:
    """
    AI moderation function.
    Returns dict with moderation results.
    """
    if not content:
        return {"flagged": False, "ai_flagged": False, "categories": []}
    
    is_toxic, confidence, categories = ai_moderator.moderate(content)
    
    return {
        "flagged": is_toxic,
        "ai_flagged": is_toxic,
        "confidence": confidence,
        "categories": categories
    }


# --- Helper Functions for Admin ---
def get_all_users():
    """Fetch all users except admins"""
    users = list(users_col.find({"role": {"$ne": "Admin"}}))  
    for user in users:
        user["_id"] = str(user["_id"])
    return users

def get_flagged_posts():
    """Fetch all flagged posts."""
    posts = list(peersupportposts_col.find({"flagged": True}).sort("datetime", -1))
    for post in posts:
        post["_id"] = str(post["_id"])
        user = users_col.find_one({"user_id": post["user_id"]})
        post["username"] = "Anonymous" if post.get("is_anonymous") else user.get("username", "Unknown")
        for reply in post.get("replies", []):
            reply["_id"] = str(reply["_id"])
            reply_user = users_col.find_one({"user_id": reply["user_id"]})
            reply["username"] = reply_user.get("username", "Unknown") if reply_user else "Unknown"
    return posts

def update_user_role(user_id, new_role):
    users_col.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": new_role}})


def get_crisis_logs():
    logs = []
    for log in crisis_col.find().sort("timestamp", -1):
        logs.append({
            "id": str(log.get("_id", ObjectId())),  # ID as string for template
            "username": log.get("username", "Unknown"),
            "ip_address": log.get("ip_address", "N/A"),
            "timestamp": log.get("timestamp").strftime("%Y-%m-%d %H:%M:%S") 
                         if isinstance(log.get("timestamp"), datetime) else str(log.get("timestamp")),
            "resolved": log.get("resolved", False),
            "resolved_at": log.get("resolved_at")
        })
    return logs



# Initialize default data
create_default_Admin()
seed_sample_data()

# --- Routes ---
@app.route("/")
def home():
    return redirect(url_for("login"))

# --- Authentication ---
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
            
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("dashboard"))
        else:
            flash("Incorrect username or password", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if users_col.find_one({"username": username}):
            flash("User already exists", "error")
        else:
            new_user = {
                "user_id": get_next_id(users_col, "user_id"),
                "username": username,
                "password_hash": generate_password_hash(password),
                "role": "student",
                "date_joined": datetime.now()
            }
            users_col.insert_one(new_user)
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for("login"))

# --- Dashboard ---
@app.route("/dashboard")
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
        journals_col.insert_one(entry)
        return jsonify({"message": "Journal added successfully", "id": entry["journal_id"]}), 201
    except Exception as e:
        return jsonify({"error": "Failed to save journal"}), 500

@app.route("/get_journals/<username>", methods=["GET"])
def get_journals(username):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    user_entries = list(journals_col.find({"user_id": session["user_id"]}).sort("journal_id", -1))
    for e in user_entries:
        e["_id"] = str(e["_id"])
        e["id"] = e["journal_id"]
        e["content"] = e["entry"]
    return jsonify(user_entries)

@app.route("/delete_journal/<int:entry_id>", methods=["DELETE"])
def delete_journal(entry_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    res = journals_col.delete_one({"journal_id": entry_id, "user_id": session["user_id"]})
    if res.deleted_count == 1:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "not found"}), 404
    

# --- Mood Tracking ---
@app.route("/save_mood", methods=["POST"])
def save_mood():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    mood = data.get("mood")
    
    valid_moods = ['Very Happy', 'Feeling Blessed', 'Happy', 'Mind Blown', 'Frustrated', 'Sad', 'Angry', 'Crying']

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
    
    moods = list(moodtracking_col.find({"user_id": session["user_id"]}).sort("datetime", 1))
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Time", "Mood"])
    
    for mood in moods:
        dt = mood["datetime"]
        writer.writerow([dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S"), mood["mood"]])
    
    output.seek(0)
    file_data = io.BytesIO()
    file_data.write(output.getvalue().encode('utf-8'))
    file_data.seek(0)
    
    return send_file(file_data, 
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=f'moods_{session["username"]}.csv')

# --- Appointments ---
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
    
    user_appointments = list(appointments_col.find({"user_id": session["user_id"]}).sort("datetime", 1))
    
    for appointment in user_appointments:
        counselor = counselors_col.find_one({"counselor_id": appointment["counselor_id"]})
        appointment["counselor_name"] = counselor["name"] if counselor else "Unknown"
        appointment["_id"] = str(appointment["_id"])
    
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

# --- Resources ---
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

@app.route("/peer")
def peer():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "peer.html",
        username=session.get("username", "Guest"),
        user_type=session.get("role", "User").lower()
    )


@app.route("/peer_data")
def peer_data():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    posts = list(peersupportposts_col.find().sort("datetime", -1))

    for post in posts:
        post["_id"] = str(post["_id"])
        user = users_col.find_one({"user_id": post["user_id"]})

        if post.get("is_deleted"):
            post["username"] = "Deleted User"
            post["content"] = "Post deleted"
        else:
            post["username"] = "Anonymous" if post.get("is_anonymous") else user.get("username", "Unknown")
            # Fix the role check to match the actual role value
            post["isstudentvol"] = (user and user.get("role") == "studentvol")

        for reply in post.get("replies", []):
            reply["_id"] = str(reply["_id"])
            reply_user = users_col.find_one({"user_id": reply["user_id"]})

            if reply.get("is_deleted"):
                reply["username"] = "Deleted User"
                reply["content"] = "Reply deleted"
            else:
                # Fix the role check to match the actual role value
                reply["isstudentvol"] = (reply_user and reply_user.get("role") == "studentvol")
                reply["username"] = reply.get("username", reply_user.get("username", "Unknown") if reply_user else "Unknown")

    return jsonify(posts)


@app.route("/add_post", methods=["POST"])
def add_post():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    content = data.get("content", "").strip()
    is_anonymous = data.get("is_anonymous", False)

    if not content:
        return jsonify({"error": "Content is required"}), 400

    user_role = session.get("role")
    
    # AI moderation
    moderation_result = check(content)
    flagged = moderation_result["flagged"]
    ai_flagged = moderation_result["ai_flagged"]
    categories = moderation_result.get("categories", [])

    post = {
        "user_id": session["user_id"],
        "datetime": datetime.now(),
        "content": content,
        "is_anonymous": bool(is_anonymous),
        "likes": [],
        "dislikes": [],
        "replies": [],
        "flagged": flagged,
        "ai_flagged": ai_flagged,
        "flag_categories": categories,
        "isstudentvol": (user_role == "studentvol"),
        "is_deleted": False
    }

    result = peersupportposts_col.insert_one(post)
    post["_id"] = str(result.inserted_id)
    return jsonify({"message": "Post added successfully!", "post": post})


@app.route("/add_reply/<post_id>", methods=["POST"])
def add_reply(post_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    reply_content = data.get("reply", "").strip()
    if not reply_content:
        return jsonify({"error": "Reply content is required"}), 400

    user = users_col.find_one({"user_id": session["user_id"]})
    username = user.get("username", "Unknown") if user else "Unknown"

    # AI moderation for replies
    moderation_result = check(reply_content)
    flagged = moderation_result["flagged"]
    ai_flagged = moderation_result["ai_flagged"]
    categories = moderation_result.get("categories", [])

    reply = {
        "_id": ObjectId(),
        "user_id": session["user_id"],
        "username": username,
        "datetime": datetime.now(),
        "content": reply_content,
        "flagged": flagged,
        "ai_flagged": ai_flagged,
        "flag_categories": categories,
        "likes": [],
        "dislikes": [],
        "isstudentvol": (session.get("role") == "studentvol"),
        "is_deleted": False
    }

    peersupportposts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$push": {"replies": reply}}
    )
    reply["_id"] = str(reply["_id"])
    return jsonify({"message": "Reply added successfully!", "reply": reply})


@app.route("/like_post/<post_id>", methods=["POST"])
def like_post(post_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    action = data.get("action")
    user_id = session["user_id"]

    post = peersupportposts_col.find_one({"_id": ObjectId(post_id)})
    if not post:
        return jsonify({"error": "Post not found"}), 404

    likes = post.get("likes", [])
    dislikes = post.get("dislikes", [])

    if action == "like":
        if user_id in likes:
            likes.remove(user_id)
        else:
            likes.append(user_id)
            if user_id in dislikes:
                dislikes.remove(user_id)
    elif action == "dislike":
        if user_id in dislikes:
            dislikes.remove(user_id)
        else:
            dislikes.append(user_id)
            if user_id in likes:
                likes.remove(user_id)
    else:
        return jsonify({"error": "Invalid action"}), 400

    peersupportposts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"likes": likes, "dislikes": dislikes}}
    )

    return jsonify({"likes": len(likes), "dislikes": len(dislikes)})


@app.route("/like_reply/<post_id>/<reply_id>", methods=["POST"])
def like_reply(post_id, reply_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    action = data.get("action")
    user_id = session["user_id"]

    post = peersupportposts_col.find_one({"_id": ObjectId(post_id)})
    if not post:
        return jsonify({"error": "Post not found"}), 404

    replies = post.get("replies", [])
    for reply in replies:
        if str(reply["_id"]) == reply_id:
            likes = reply.get("likes", [])
            dislikes = reply.get("dislikes", [])

            if action == "like":
                if user_id in likes:
                    likes.remove(user_id)
                else:
                    likes.append(user_id)
                    if user_id in dislikes:
                        dislikes.remove(user_id)
            elif action == "dislike":
                if user_id in dislikes:
                    dislikes.remove(user_id)
                else:
                    dislikes.append(user_id)
                    if user_id in likes:
                        likes.remove(user_id)
            else:
                return jsonify({"error": "Invalid action"}), 400

            reply["likes"] = likes
            reply["dislikes"] = dislikes

    peersupportposts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"replies": replies}}
    )

    return jsonify({"message": "Action recorded"})


# --- Soft delete for users ---
# --- User deleting own post ---
@app.route("/delete_post/<post_id>", methods=["DELETE"])
def delete_own_post(post_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    try:
        post = peersupportposts_col.find_one({"_id": ObjectId(post_id)})
        if not post:
            return jsonify({"error": "Post not found"}), 404

        # Convert both IDs to strings for comparison
        post_user_id = str(post["user_id"])
        session_user_id = str(session["user_id"])
        user_role = session.get("role")

        # Allow deletion if it's the owner's post OR if user is an Admin OR studentvol
        if (post_user_id != session_user_id and 
            user_role not in ["Admin", "studentvol"]):
            return jsonify({"error": "Unauthorized"}), 403

        # Soft delete for owners, hard delete for Admins and studentvols
        if user_role in ["Admin", "studentvol"]:
            peersupportposts_col.delete_one({"_id": ObjectId(post_id)})
            return jsonify({"message": "Post permanently deleted"})
        else:
            peersupportposts_col.update_one(
                {"_id": ObjectId(post_id)},
                {"$set": {"content": "Post deleted", "is_deleted": True}}
            )
            return jsonify({"message": "Post deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- User deleting own reply ---
@app.route("/delete_reply/<post_id>/<reply_id>", methods=["DELETE"])
def delete_own_reply(post_id, reply_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    post = peersupportposts_col.find_one({"_id": ObjectId(post_id)})
    if not post:
        return jsonify({"error": "Post not found"}), 404

    replies = post.get("replies", [])
    updated = False
    user_role = session.get("role")

    for reply in replies:
        if str(reply["_id"]) == reply_id:
            # Allow deletion if owner OR Admin OR studentvol
            if (str(reply["user_id"]) != str(session["user_id"]) and 
                user_role not in ["Admin", "studentvol"]):
                return jsonify({"error": "Unauthorized"}), 403

            if user_role in ["Admin", "studentvol"]:
                replies = [r for r in replies if str(r["_id"]) != reply_id]  # remove reply entirely
                updated = True
            else:
                reply["content"] = "Reply deleted"
                reply["is_deleted"] = True
                updated = True
            break

    if not updated:
        return jsonify({"error": "Reply not found"}), 404

    peersupportposts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"replies": replies}}
    )

    return jsonify({"message": "Reply deleted"})


# --- Flag content (studentvol only) ---
@app.route("/flag_content/<content_type>/<content_id>", methods=["POST"])
def flag_content(content_type, content_id):
    if "user_id" not in session or session.get("role") != "studentvol":
        return jsonify({"error": "studentvol access required"}), 403

    try:
        if content_type == "post":
            result = peersupportposts_col.update_one(
                {"_id": ObjectId(content_id)},
                {"$set": {"flagged": True, "ai_flagged": False}}
            )
            if result.modified_count == 1:
                return jsonify({"message": "Post flagged successfully"})
            else:
                return jsonify({"error": "Post not found"}), 404
                
        elif content_type == "reply":
            # For replies, we need to find the post first
            post = peersupportposts_col.find_one({"replies._id": ObjectId(content_id)})
            if not post:
                return jsonify({"error": "Reply not found"}), 404
                
            # Update the specific reply's flagged status
            result = peersupportposts_col.update_one(
                {"_id": post["_id"], "replies._id": ObjectId(content_id)},
                {"$set": {"replies.$.flagged": True, "replies.$.ai_flagged": False}}
            )
            
            if result.modified_count == 1:
                return jsonify({"message": "Reply flagged successfully"})
            else:
                return jsonify({"error": "Failed to flag reply"}), 500
                
        else:
            return jsonify({"error": "Invalid content type"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Unflag content (Admin and studentvol) ---
@app.route("/unflag_content/<content_type>/<content_id>", methods=["POST"])
def unflag_content(content_type, content_id):
    if "user_id" not in session or session.get("role") not in ["Admin", "studentvol"]:
        return jsonify({"error": "Admin or studentvol access required"}), 403

    try:
        if content_type == "post":
            result = peersupportposts_col.update_one(
                {"_id": ObjectId(content_id)},
                {"$set": {"flagged": False, "ai_flagged": False, "flag_categories": []}}
            )
            if result.modified_count == 1:
                return jsonify({"message": "Post unflagged successfully"})
            else:
                return jsonify({"error": "Post not found"}), 404
                
        elif content_type == "reply":
            # For replies, we need to find the post first
            post = peersupportposts_col.find_one({"replies._id": ObjectId(content_id)})
            if not post:
                return jsonify({"error": "Reply not found"}), 404
                
            # Update the specific reply's flagged status
            result = peersupportposts_col.update_one(
                {"_id": post["_id"], "replies._id": ObjectId(content_id)},
                {"$set": {
                    "replies.$.flagged": False, 
                    "replies.$.ai_flagged": False,
                    "replies.$.flag_categories": []
                }}
            )
            
            if result.modified_count == 1:
                return jsonify({"message": "Reply unflagged successfully"})
            else:
                return jsonify({"error": "Failed to unflag reply"}), 500
                
        else:
            return jsonify({"error": "Invalid content type"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Admin-only moderation (hard delete) ---
@app.route("/moderate/delete/<post_id>", methods=["DELETE"])
def admin_delete_post(post_id):
    if "user_id" not in session or session.get("role") != "Admin":
        return jsonify({"error": "Admin access required"}), 403

    peersupportposts_col.delete_one({"_id": ObjectId(post_id)})
    return jsonify({"message": "Post permanently deleted"})


#---Crisis---

@app.route("/crisis", methods=["POST"])
def crisis():
    if "username" not in session:
        return jsonify({"error": "Not logged in"}), 401

    username = session["username"]
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)

    crisis_doc = {
        "username": username,
        "ip_address": ip_address,
        "timestamp": datetime.utcnow()
    }
    db["crisis"].insert_one(crisis_doc)

    return jsonify({"message": "Crisis logged successfully"})


@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    if request.method == "POST":
        user_id = request.form.get("user_id")
        new_role = request.form.get("role")
        if user_id and new_role:
            update_user_role(user_id, new_role)

    stats = {
        "total_users": users_col.count_documents({"role": {"$ne": "admin"}}),
        "total_journals": journals_col.count_documents({}),
        "total_appointments": appointments_col.count_documents({}),
        "total_posts": peersupportposts_col.count_documents({})
    }

    users = get_all_users()
    logs = get_crisis_logs()
    

    return render_template(
        "admin_dashboard.html",
        username=session["username"],
        stats=stats,    
        users=users,
        crisis_logs=logs
    )



@app.route("/Admin/users", methods=["GET", "POST"])
def manage_users():
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return "Unauthorized", 403

    if request.method == "POST":
        user_id = request.form.get("user_id")
        new_role = request.form.get("role")
        if user_id and new_role:
            update_user_role(user_id, new_role)

    users = get_all_users()  # fetch only non-admin users
    return render_template("admin_dashboard.html", users=users)

@app.route("/Admin/flagged_posts", methods=["GET", "POST"])
def Admin_flagged_posts():
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return "Unauthorized", 403

    if request.method == "POST":
        action = request.form.get("action")  # delete/unflag
        post_id = request.form.get("post_id")
        if action == "delete" and post_id:
            peersupportposts_col.delete_one({"_id": ObjectId(post_id)})
        elif action == "unflag" and post_id:
            peersupportposts_col.update_one({"_id": ObjectId(post_id)}, {"$set": {"flagged": False}})

    posts = get_flagged_posts()
    return render_template("Admin_flagged_posts.html", posts=posts)

@app.route("/admin/crisis_logs", methods=["GET"])
def get_crisis_logs():
    logs = []
    for log in crisis_col.find().sort("timestamp", -1):
        logs.append({
            "id": str(log.get("_id", ObjectId())),  # ID as string for template
            "username": log.get("username", "Unknown"),
            "ip_address": log.get("ip_address", "N/A"),
            "timestamp": log.get("timestamp").strftime("%Y-%m-%d %H:%M:%S") 
                         if isinstance(log.get("timestamp"), datetime) else str(log.get("timestamp")),
            "resolved": log.get("resolved", False),
            "resolved_at": log.get("resolved_at")
        })
    return logs
    


@app.route("/resolve_crisis/<log_id>", methods=["POST"])
def resolve_crisis(log_id):
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    try:
        result = crisis_col.update_one(
            {"_id": ObjectId(log_id)},
            {"$set": {"resolved": True, "resolved_at": datetime.now()}}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Crisis log not found"}), 404

        return jsonify({"message": "Crisis log resolved successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Debug ---
@app.route("/debug/all_collections")
def debug_all_collections():
    if "user_id" not in session or session["role"] != "Admin":
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        collections_info = {}
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
    
@app.route('/appointment')
def appointment():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('booking.html', username=session['username'])


@app.route('/api/therapists', methods=['GET'])
def get_therapists():
    docs = list(therapists_col.find({}))
    result = []
    for d in docs:
        result.append({
            "_id": str(d["_id"]),
            "name": d.get("name"),
            "expertise": d.get("expertise"),
            "years_experience": d.get("years_experience"),
            "location": d.get("location")
        })
    return jsonify(result), 200

@app.route('/api/therapists/<therapist_id>/slots', methods=['GET'])
def get_slots(therapist_id):
    date = request.args.get('date')
    if not date:
        abort(400, "Missing date param")
    try:
        # find slots for therapist + date
        t_oid = ObjectId(therapist_id)
    except:
        abort(400, "Invalid therapist id")
    docs = list(slots_col.find({"therapist_id": t_oid, "date": date}))
    slots = []
    for s in docs:
        slots.append({
            "_id": str(s["_id"]),
            "therapist_id": str(s["therapist_id"]),
            "date": s["date"],
            "time": s["time"],
            "status": s.get("status", "available"),
            "booked_by": s.get("booked_by")  # can be user id
        })
    return jsonify({"slots": slots}), 200

@app.route('/api/book', methods=['POST'])
def book_slot():
    payload = request.get_json() or {}
    therapist_id = payload.get('therapist_id')   # may be null -> server auto-match
    slot_id = payload.get('slot_id')             # optional: if client selected exact slot
    date = payload.get('date')
    time = payload.get('time')
    user_id = payload.get('user_id')
    session_type = payload.get('session_type', 'individual')
    concerns = payload.get('concerns', '')

    if not date or not time or not user_id:
        return jsonify({"error":"Missing fields"}), 400

    # If slot_id provided, attempt atomic update: only mark booked if status == 'available'
    if slot_id:
        try:
            s_oid = ObjectId(slot_id)
        except:
            return jsonify({"error":"Invalid slot id"}), 400

        res = slots_col.update_one(
            {"_id": s_oid, "status": "available"},
            {"$set": {"status": "booked", "booked_by": user_id, "booked_at": datetime.utcnow()}}
        )
        if res.modified_count == 0:
            return jsonify({"error":"Slot already booked or unavailable"}), 409

        # create booking record
        booking = {
          "slot_id": s_oid,
          "therapist_id": ObjectId(therapist_id),
          "user_id": user_id,
          "date": date,
          "time": time,
          "session_type": session_type,
          "concerns": concerns,
          "created_at": datetime.utcnow()
        }
        booking_id = bookings_col.insert_one(booking).inserted_id
        return jsonify({
            "message": "Booked",
            "booking_id": str(booking_id),
            "therapist_id": therapist_id,
            "slot_id": str(s_oid),
            "date": date,
            "time": time
        }), 200

    # If no slot_id, attempt server-side find+book: find first available slot for therapist on that date/time
    if therapist_id:
        try:
            t_oid = ObjectId(therapist_id)
        except:
            return jsonify({"error":"Invalid therapist id"}),400
        # find a slot for that exact time and date and try to book
        res = slots_col.update_one(
            {"therapist_id": t_oid, "date": date, "time": time, "status": "available"},
            {"$set": {"status": "booked", "booked_by": user_id, "booked_at": datetime.utcnow()}}
        )
        if res.modified_count == 0:
            return jsonify({"error":"Slot not available"}), 409
        # find the slot doc now
        s = slots_col.find_one({"therapist_id": t_oid, "date": date, "time": time})
        booking = {
          "slot_id": s["_id"],
          "therapist_id": t_oid,
          "user_id": user_id,
          "date": date,
          "time": time,
          "session_type": session_type,
          "concerns": concerns,
          "created_at": datetime.utcnow()
        }
        booking_id = bookings_col.insert_one(booking).inserted_id
        return jsonify({
            "message":"Booked",
            "booking_id": str(booking_id),
            "therapist_id": therapist_id,
            "slot_id": str(s["_id"]),
            "date": date,
            "time": time
        }), 200

    # Auto-match: if therapist_id omitted, find any therapist with available slot for date/time
    # (basic example: first matching slot)
    slot_doc = slots_col.find_one_and_update(
      {"date": date, "time": time, "status": "available"},
      {"$set": {"status": "booked", "booked_by": user_id, "booked_at": datetime.utcnow()}}
    )
    if not slot_doc:
      return jsonify({"error":"No available slots"}), 409
    booking = {
      "slot_id": slot_doc["_id"],
      "therapist_id": slot_doc["therapist_id"],
      "user_id": user_id,
      "date": date,
      "time": time,
      "session_type": session_type,
      "concerns": concerns,
      "created_at": datetime.utcnow()
    }
    bid = bookings_col.insert_one(booking).inserted_id
    return jsonify({"message":"Booked", "booking_id": str(bid), "therapist_id": str(slot_doc["therapist_id"]), "slot_id": str(slot_doc["_id"]), "date": date, "time": time}), 200


# Utility: safe ObjectId -> str
def oid_to_str(oid):
    return str(oid) if oid is not None else None

# -----------------------
# GET /api/proctors
# -----------------------
# Returns a list of proctors
# Response: [{ _id, name, expertise, department, years_experience, location, ...}, ...]
@app.route('/api/proctors', methods=['GET'])
def get_proctors():
    try:
        docs = list(proctors_col.find({}))
        out = []
        for d in docs:
            out.append({
                "_id": oid_to_str(d.get("_id")),
                "name": d.get("name"),
                "expertise": d.get("expertise"),
                "department": d.get("department"),
                "years_experience": d.get("years_experience"),
                "location": d.get("location"),
                "contact": d.get("contact")
            })
        return jsonify(out), 200
    except Exception as e:
        app.logger.exception("Failed to fetch proctors")
        return jsonify({"error": "Internal server error"}), 500


# -----------------------
# GET /api/proctors/<proctor_id>/slots?date=YYYY-MM-DD
# -----------------------
# Returns slots for the specified proctor on a date.
# Response: { slots: [ { _id, proctor_id, date, time, status, booked_by }, ... ] }
@app.route('/api/proctors/<proctor_id>/slots', methods=['GET'])
def get_proctor_slots(proctor_id):
    date = request.args.get('date')
    if not date:
        return jsonify({"error": "Missing required query param: date (YYYY-MM-DD)"}), 400

    # basic date-format validation (YYYY-MM-DD)
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    try:
        p_oid = ObjectId(proctor_id)
    except Exception:
        return jsonify({"error": "Invalid proctor id"}), 400

    try:
        docs = list(slots_col.find({"proctor_id": p_oid, "date": date}))
        slots = []
        for s in docs:
            slots.append({
                "_id": oid_to_str(s.get("_id")),
                "proctor_id": oid_to_str(s.get("proctor_id")),
                "date": s.get("date"),
                "time": s.get("time"),
                "status": s.get("status", "available"),
                "booked_by": s.get("booked_by")
            })
        return jsonify({"slots": slots}), 200
    except Exception as e:
        app.logger.exception("Failed to fetch proctor slots")
        return jsonify({"error": "Internal server error"}), 500


# -----------------------
# GET /api/bookings?user_id=<user_id>
# -----------------------
# Returns bookings for a user. If no user_id provided, returns empty (or admin can query all).
# Each booking includes: _id, role ('therapist'|'proctor'), name (therapist/proctor name), date, time, status, created_at
@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id query parameter"}), 400

    try:
        docs = list(bookings_col.find({"user_id": user_id}))
        out = []
        for b in docs:
            # determine role & name
            role = 'therapist' if b.get('therapist_id') else ('proctor' if b.get('proctor_id') else 'unknown')
            name = None
            extra = None
            if role == 'therapist' and b.get('therapist_id'):
                try:
                    t = db.therapists.find_one({"_id": ObjectId(b['therapist_id'])})
                    name = t.get('name') if t else None
                    extra = t.get('expertise') if t else None
                except Exception:
                    name = None
            elif role == 'proctor' and b.get('proctor_id'):
                try:
                    p = proctors_col.find_one({"_id": ObjectId(b['proctor_id'])})
                    name = p.get('name') if p else None
                    extra = p.get('department') if p else None
                except Exception:
                    name = None

            out.append({
                "_id": oid_to_str(b.get("_id")),
                "role": role,
                "name": name or b.get("name") or "",
                "extra": extra or "",
                "date": b.get("date"),
                "time": b.get("time"),
                "status": b.get("status", "confirmed"),
                "slot_id": oid_to_str(b.get("slot_id")),
                "created_at": b.get("created_at").isoformat() if isinstance(b.get("created_at"), datetime) else b.get("created_at")
            })
        # optionally sort by date/time ascending
        out.sort(key=lambda x: (x.get("date") or "", x.get("time") or ""))
        return jsonify(out), 200
    except Exception as e:
        app.logger.exception("Failed to fetch bookings")
        return jsonify({"error": "Internal server error"}), 500


# -----------------------
# OPTIONAL: helper endpoint to seed a proctor (dev only)
# -----------------------
@app.route('/api/admin/seed_proctor', methods=['POST'])
def seed_proctor():
    payload = request.get_json() or {}
    name = payload.get('name') or 'Dr. Test Proctor'
    doc = {
        "name": name,
        "expertise": payload.get('expertise', 'Exam proctoring'),
        "department": payload.get('department', 'Exams'),
        "years_experience": payload.get('years_experience', 3),
        "location": payload.get('location', 'Campus'),
        "contact": payload.get('contact', {})
    }
    res = proctors_col.insert_one(doc)
    return jsonify({"inserted_id": oid_to_str(res.inserted_id)}), 201

# Login session verification
@app.route("/session_info")
def session_info():
    if "user_id" not in session:
        return jsonify({})
    return jsonify({
        "user_id": str(session["user_id"]),
        "username": session.get("username"),
        "role": session.get("role", "User")
    })

# --- Run App ---
if __name__ == "__main__":
    app.run(debug=True)