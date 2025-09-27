from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, abort
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from werkzeug.security import generate_password_hash, check_password_hash
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.message import EmailMessage
from chatbot import EmotionalChatbot
from flask import Flask, jsonify
import sentiment_analysis as sa
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
from flask_cors import CORS
from bson import ObjectId
from bson.son import SON
import traceback
import logging
import smtplib
import torch
import uuid
import re
import json
import csv
import os
import io

import subprocess
import tempfile
from google.cloud import speech_v1 as speech


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
crisis_col = db["crisis"]
assess_col = db["assessments"]   # stores PH
sessions_col = db["sessions"]
page_views_col = db["page_views"] 
mood_entries_col = db["mood_entries"]


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

# def seed_sample_data():
#     """Add sample counselors and resources if collections are empty"""
#     # Sample Counselors
#     if counselors_col.count_documents({}) == 0:
#         sample_counselors = [
#             {
#                 "counselor_id": 1,
#                 "name": "Dr. Sarah Johnson",
#                 "specialization": "Anxiety & Depression",
#                 "contact_info": "sarah.johnson@soulace.com"
#             },
#             {
#                 "counselor_id": 2,
#                 "name": "Dr. Michael Chen",
#                 "specialization": "Trauma Counseling",
#                 "contact_info": "michael.chen@soulace.com"
#             },
#             {
#                 "counselor_id": 3,
#                 "name": "Dr. Emily Rodriguez",
#                 "specialization": "Family Therapy",
#                 "contact_info": "emily.rodriguez@soulace.com"
#             }
#         ]
#         counselors_col.insert_many(sample_counselors)
#         print("✅ Sample counselors added")

    # Sample Resources
    # if resources_col.count_documents({}) == 0:
    #     sample_resources = [
    #         {
    #             "resource_id": 1,
    #             "title": "Managing Anxiety: A Complete Guide",
    #             "type": "Guide",
    #             "language": "English",
    #             "url": "https://example.com/anxiety-guide"
    #         },
    #         {
    #             "resource_id": 2,
    #             "title": "Meditation for Beginners",
    #             "type": "Audio",
    #             "language": "English",
    #             "url": "https://example.com/meditation-audio"
    #         },
    #         {
    #             "resource_id": 3,
    #             "title": "Stress Relief Techniques",
    #             "type": "Video",
    #             "language": "English",
    #             "url": "https://example.com/stress-video"
    #         }
    #     ]
    #     resources_col.insert_many(sample_resources)
    #     print("✅ Sample resources added")

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
    users = list(users_col.find({"role": {"$ne": "admin"}}))  
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
# seed_sample_data()

# --- Routes ---
@app.route("/")
def welcome():
    return render_template("welcome.html")

@app.route("/welcome")
def welcome_page():
    return render_template("welcome.html")

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
        confirm_password = request.form.get("confirm_password")
        
        
        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template("register.html")
        
        # Check if username already exists
        if users_col.find_one({"username": username}):
            flash("Username already exists", "error")
            return render_template("register.html")
        
        # Create new user
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

@app.route("/api/check_username", methods=["POST"])
def check_username():
    data = request.get_json()
    username = data.get("username", "").strip()
    
    # Check if username exists in database
    existing_user = users_col.find_one({"username": username})
    
    return jsonify({
        "available": existing_user is None,
        "username": username
    })

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
    
    print("Logging visit...")
    db.page_views.insert_one({
        "page": "dashboard",
        "timestamp": datetime.now(),
    })
    return render_template("dashboard.html", username=session["username"])

# --- Journal Routes ---
# @app.route("/journal")
# def journal():
#     if "user_id" not in session:
#         flash("Please login to access journals", "warning")
#         return redirect(url_for("login"))
#     return render_template("journal.html", username=session["username"])

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

        if mood in ["Sad", "Angry"]:
            journaling_prompt = (
                "I'm sorry you're feeling this way. "
                "What do you think contributed to this feeling? "
                "Would you like to write about what might help you feel better?"
            )
        elif mood == "Happy":
            journaling_prompt = (
                "That's wonderful! What made you feel this way today? "
                "Would you like to write it down so you can revisit it later?"
            )
        elif mood == "Calm":
            journaling_prompt = (
                "It's great that you're feeling peaceful. "
                "What helped you achieve this sense of calm today?"
            )
        elif mood == "Void":
            journaling_prompt = (
                "Sometimes feeling neutral is perfectly okay. "
                "Would you like to explore what's on your mind right now?"
            )

    # ✅ Render journal template with prompt
    return render_template("journal.html", journaling_prompt=journaling_prompt, username = session["username"])


@app.route("/add_journal", methods=["POST"])
def add_journal():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    # Handle both JSON and form data (for audio uploads)
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        # Audio entry
        title = request.form.get("title", "").strip()
        entry_type = request.form.get("type", "text")
        audio_file = request.files.get("audio")

        if not title or not audio_file:
            return jsonify({"error": "Title and audio file are required"}), 400

        now = datetime.now()
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M:%S")

        # Create audio directory if it doesn't exist
        audio_dir = os.path.join("static", "audio")
        os.makedirs(audio_dir, exist_ok=True)

        # Save audio file with unique name
        journal_id = get_next_id(journals_col, "journal_id")
        filename = f"audio_{journal_id}_{session['user_id']}.wav"
        audio_path = os.path.join(audio_dir, filename)
        audio_file.save(audio_path)

        entry = {
            "journal_id": journal_id,
            "user_id": session["user_id"],
            "title": title,
            "type": "audio",
            "audio_file": filename,
            "datetime": now,
            "is_edited": False,
            "date": date,
            "time": time
        }
    else:
        # Text entry
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
            "type": "text",
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
        # Handle both text and audio entries
        if e.get("type") == "audio":
            e["content"] = None  # Audio entries don't have text content
        else:
            e["content"] = e.get("entry", "")
            e["type"] = "text"  # Ensure old entries have type
    return jsonify(user_entries)

@app.route("/get_audio/<int:entry_id>")
def get_audio(entry_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    entry = journals_col.find_one({"journal_id": entry_id, "user_id": session["user_id"], "type": "audio"})
    if not entry or not entry.get("audio_file"):
        abort(404)

    audio_path = os.path.join("static", "audio", entry["audio_file"])
    if os.path.exists(audio_path):
        return send_file(audio_path, as_attachment=False)
    else:
        abort(404)

@app.route("/delete_journal/<int:entry_id>", methods=["DELETE"])
def delete_journal(entry_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    # Find the entry first to check if it's an audio entry
    entry = journals_col.find_one({"journal_id": entry_id, "user_id": session["user_id"]})
    if not entry:
        return jsonify({"success": False, "error": "not found"}), 404

    # Delete audio file if it exists
    if entry.get("type") == "audio" and entry.get("audio_file"):
        audio_path = os.path.join("static", "audio", entry["audio_file"])
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception as e:
                print(f"Failed to delete audio file: {e}")

    # Delete the database entry
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
    
    # ✅ Define valid moods (matching SVG files)
    valid_moods = ["Happy", "Calm", "Void", "Sad", "Angry"]
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
    if mood in ["Sad", "Angry"]:
        journaling_prompt = (
            "I'm sorry you're feeling this way. "
            "What do you think contributed to this feeling? "
            "Would you like to write about what might help you feel better?"
        )
    elif mood == "Happy":
        journaling_prompt = (
            "That's wonderful! What made you feel this way today? "
            "Would you like to write it down so you can revisit it later?"
        )
    elif mood == "Calm":
        journaling_prompt = (
            "It's great that you're feeling peaceful. "
            "What helped you achieve this sense of calm today?"
        )
    elif mood == "Void":
        journaling_prompt = (
            "Sometimes feeling neutral is perfectly okay. "
            "Would you like to explore what's on your mind right now?"
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


@app.route("/download_chart", methods=["GET"])
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
    except Exception:
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
    """
    Payload (preferred):
      {
        therapist_id: <optional ObjectId string>,
        proctor_id: <optional ObjectId string>,
        slot_id: <optional slot _id string>,
        date: "YYYY-MM-DD",
        time: "HH:MM",
        concerns: "...",
        session_type: "individual" (optional)
      }
    The server will prefer session['user_id'] as the booking user.
    """
    payload = request.get_json() or {}
    therapist_id = payload.get('therapist_id')
    proctor_id = payload.get('proctor_id')
    slot_id = payload.get('slot_id')
    date = payload.get('date')
    time = payload.get('time')
    concerns = payload.get('concerns', '')
    session_type = payload.get('session_type', 'individual')

    # authoritative: prefer session user id
    user_id = session.get('user_id') or payload.get('user_id')
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not date or not time:
        return jsonify({"error": "Missing date/time"}), 400

    # Helper to wrap string -> ObjectId safely
    def to_oid(val):
        try:
            return ObjectId(val)
        except Exception:
            return None

    # 1) If slot_id provided: attempt atomic update of that slot (works for therapist or proctor slots)
    if slot_id:
        s_oid = to_oid(slot_id)
        if not s_oid:
            return jsonify({"error": "Invalid slot id"}), 400

        # We don't know whether this slot belongs to therapist or proctor - update only if status available
        res = slots_col.update_one(
            {"_id": s_oid, "status": "available"},
            {"$set": {"status": "booked", "booked_by": user_id, "booked_at": datetime.utcnow()}}
        )
        if res.modified_count == 0:
            return jsonify({"error": "Slot already booked or unavailable"}), 409

        # fetch slot doc to determine owner (therapist/proctor)
        slot_doc = slots_col.find_one({"_id": s_oid})
        if not slot_doc:
            return jsonify({"error": "Slot not found after booking update"}), 500

        # construct booking document
        booking = {
            "slot_id": slot_doc["_id"],
            "therapist_id": slot_doc.get("therapist_id"),
            "proctor_id": slot_doc.get("proctor_id"),
            "user_id": user_id,
            "date": slot_doc.get("date", date),
            "time": slot_doc.get("time", time),
            "session_type": session_type,
            "concerns": concerns,
            "status": "confirmed",
            "created_at": datetime.utcnow()
        }
        booking_id = bookings_col.insert_one(booking).inserted_id
        return jsonify({
            "message": "Booked",
            "booking_id": str(booking_id),
            "slot_id": str(s_oid),
            "date": booking["date"],
            "time": booking["time"]
        }), 200

    # 2) If therapist_id/proctor_id provided + date/time: try to book a matching available slot
    if therapist_id or proctor_id:
        if therapist_id:
            owner_field = "therapist_id"
            owner_oid = to_oid(therapist_id)
        else:
            owner_field = "proctor_id"
            owner_oid = to_oid(proctor_id)

        if not owner_oid:
            return jsonify({"error": "Invalid person id"}), 400

        query = { owner_field: owner_oid, "date": date, "time": time, "status": "available" }
        res = slots_col.update_one(
            query,
            {"$set": {"status": "booked", "booked_by": user_id, "booked_at": datetime.utcnow()}}
        )
        if res.modified_count == 0:
            return jsonify({"error": "Slot not available"}), 409

        # fetch booked slot to include in booking
        s = slots_col.find_one({ owner_field: owner_oid, "date": date, "time": time })
        if not s:
            return jsonify({"error": "Slot booked but cannot retrieve slot document"}), 500

        booking = {
            "slot_id": s["_id"],
            "therapist_id": s.get("therapist_id"),
            "proctor_id": s.get("proctor_id"),
            "user_id": user_id,
            "date": s.get("date"),
            "time": s.get("time"),
            "session_type": session_type,
            "concerns": concerns,
            "status": "confirmed",
            "created_at": datetime.utcnow()
        }
        booking_id = bookings_col.insert_one(booking).inserted_id
        return jsonify({
            "message": "Booked",
            "booking_id": str(booking_id),
            "slot_id": str(s["_id"]),
            "date": s.get("date"),
            "time": s.get("time")
        }), 200

    # 3) Auto-match (no specific person): try to find any available slot for that date/time
    slot_doc = slots_col.find_one_and_update(
        {"date": date, "time": time, "status": "available"},
        {"$set": {"status": "booked", "booked_by": user_id, "booked_at": datetime.utcnow()}}
    )
    if not slot_doc:
        return jsonify({"error": "No available slots"}), 409

    booking = {
        "slot_id": slot_doc["_id"],
        "therapist_id": slot_doc.get("therapist_id"),
        "proctor_id": slot_doc.get("proctor_id"),
        "user_id": user_id,
        "date": slot_doc.get("date"),
        "time": slot_doc.get("time"),
        "session_type": session_type,
        "concerns": concerns,
        "status": "confirmed",
        "created_at": datetime.utcnow()
    }
    bid = bookings_col.insert_one(booking).inserted_id
    return jsonify({
        "message":"Booked",
        "booking_id": str(bid),
        "slot_id": str(slot_doc["_id"]),
        "date": slot_doc.get("date"),
        "time": slot_doc.get("time")
    }), 200

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
    # prefer explicit query param, else use session user
    user_id = request.args.get('user_id') or session.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id (or not logged in)"}), 400

    try:
        docs = list(bookings_col.find({"user_id": user_id}))
        out = []
        for b in docs:
            role = 'therapist' if b.get('therapist_id') else ('proctor' if b.get('proctor_id') else 'unknown')
            name = None
            extra = None
            if role == 'therapist' and b.get('therapist_id'):
                try:
                    t = therapists_col.find_one({"_id": ObjectId(b['therapist_id'])}) if isinstance(b.get('therapist_id'), str) else therapists_col.find_one({"_id": b['therapist_id']})
                    name = t.get('name') if t else None
                    extra = t.get('expertise') if t else None
                except Exception:
                    name = None
            elif role == 'proctor' and b.get('proctor_id'):
                try:
                    p = proctors_col.find_one({"_id": ObjectId(b['proctor_id'])}) if isinstance(b.get('proctor_id'), str) else proctors_col.find_one({"_id": b['proctor_id']})
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

@app.route('/api/bookings/<booking_id>/cancel', methods=['POST'])
def cancel_booking(booking_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    # ensure booking exists
    try:
        b_oid = ObjectId(booking_id)
    except Exception:
        return jsonify({"error": "Invalid booking id"}), 400

    booking = bookings_col.find_one({"_id": b_oid})
    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    # check ownership (user who booked) or Admin
    if str(booking.get("user_id")) != str(session["user_id"]) and session.get("role") != "admin":
        return jsonify({"error": "Unauthorized to cancel this booking"}), 403

    # mark booking cancelled
    bookings_col.update_one({"_id": b_oid}, {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}})

    # release the slot if one exists
    slot_id = booking.get("slot_id")
    if slot_id:
        try:
            s_oid = slot_id if isinstance(slot_id, ObjectId) else ObjectId(slot_id)
            # set slot status back to available and clear booked_by/booked_at
            slots_col.update_one(
                {"_id": s_oid},
                {"$set": {"status": "available"}, "$unset": {"booked_by": "", "booked_at": ""}}
            )
        except Exception as e:
            # slot may have been removed or changed - log and continue
            app.logger.exception("Failed to release slot during cancellation: %s", e)

    return jsonify({"message": "Booking cancelled"}), 200


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
            user_role not in ["admin", "studentvol"]):
            return jsonify({"error": "Unauthorized"}), 403

        # Soft delete for owners, hard delete for Admins and studentvols
        if user_role in ["admin", "studentvol"]:
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
                user_role not in ["admin", "studentvol"]):
                return jsonify({"error": "Unauthorized"}), 403

            if user_role in ["admin", "studentvol"]:
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
    if "user_id" not in session or session.get("role") not in ["admin", "studentvol"]:
        return jsonify({"error": "admin or studentvol access required"}), 403

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
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "admin access required"}), 403

    peersupportposts_col.delete_one({"_id": ObjectId(post_id)})
    return jsonify({"message": "Post permanently deleted"})

# --- Enhanced Flagged Posts API ---
@app.route("/admin/api/flagged_posts", methods=["GET"])
def api_get_flagged_posts():
    """API endpoint to get flagged posts with filtering and pagination"""
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return jsonify({'ok': False, 'error': 'Admin access required'}), 403

    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        filter_type = request.args.get('type', 'all')  # all, ai, manual, unresolved
        filter_category = request.args.get('category', 'all')
        search_text = request.args.get('search', '').strip()

        # Build query
        query = {}

        # Filter by flag type
        if filter_type == 'ai':
            query['ai_flagged'] = True
        elif filter_type == 'manual':
            query['flagged'] = True
            query['ai_flagged'] = {'$ne': True}
        elif filter_type == 'unresolved':
            query['$or'] = [
                {'flagged': True},
                {'ai_flagged': True}
            ]
            query['resolved'] = {'$ne': True}
        else:  # all flagged
            query['$or'] = [
                {'flagged': True},
                {'ai_flagged': True}
            ]

        # Filter by AI category
        if filter_category != 'all' and filter_category:
            query['flag_categories'] = {'$in': [filter_category]}

        # Search in content
        if search_text:
            search_query = {'$or': [
                {'content': {'$regex': search_text, '$options': 'i'}},
                {'title': {'$regex': search_text, '$options': 'i'}},
                {'username': {'$regex': search_text, '$options': 'i'}}
            ]}
            if '$or' in query:
                query = {'$and': [query, search_query]}
            else:
                query.update(search_query)

        # Get total count for pagination
        total_count = peersupportposts_col.count_documents(query)
        total_pages = (total_count + per_page - 1) // per_page

        # Get posts with pagination
        skip = (page - 1) * per_page
        posts_cursor = peersupportposts_col.find(query).sort('datetime', -1).skip(skip).limit(per_page)

        posts = []
        for post in posts_cursor:
            # Serialize post
            post['_id'] = str(post['_id'])

            # Get user info
            user = users_col.find_one({"user_id": post["user_id"]})
            post["username"] = "Anonymous" if post.get("is_anonymous") else (user.get("username", "Unknown") if user else "Unknown")
            post["isstudentvol"] = user.get("role") == "studentvol" if user else False

            # Serialize replies
            for reply in post.get("replies", []):
                if "_id" in reply:
                    reply["_id"] = str(reply["_id"])
                if "id" in reply and hasattr(reply["id"], 'binary'):
                    reply["id"] = str(reply["id"])

                # Get reply user info
                reply_user = users_col.find_one({"user_id": reply["user_id"]})
                reply["author"] = reply_user.get("username", "Unknown") if reply_user else "Unknown"
                reply["isstudentvol"] = reply_user.get("role") == "studentvol" if reply_user else False

            posts.append(post)

        # Get statistics
        stats = get_flagged_posts_stats()

        # Pagination info
        pagination = {
            'current_page': page,
            'total_pages': total_pages,
            'total_posts': total_count,
            'per_page': per_page
        }

        return jsonify({
            'ok': True,
            'posts': posts,
            'stats': stats,
            'pagination': pagination
        })

    except Exception as e:
        print(f"Error getting flagged posts: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to load flagged posts'}), 500

def get_flagged_posts_stats():
    """Get statistics about flagged posts"""
    try:
        # Count AI flagged posts
        ai_flagged_count = peersupportposts_col.count_documents({'ai_flagged': True})

        # Count manually flagged posts
        manual_flagged_count = peersupportposts_col.count_documents({
            'flagged': True,
            'ai_flagged': {'$ne': True}
        })

        # Total flagged
        total_flagged = peersupportposts_col.count_documents({
            '$or': [
                {'flagged': True},
                {'ai_flagged': True}
            ]
        })

        # Resolved today
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        resolved_today = peersupportposts_col.count_documents({
            'resolved': True,
            'resolved_at': {'$gte': today_start}
        })

        return {
            'ai_flagged': ai_flagged_count,
            'manual_flagged': manual_flagged_count,
            'total_flagged': total_flagged,
            'resolved_today': resolved_today
        }

    except Exception as e:
        print(f"Error getting flagged posts stats: {str(e)}")
        return {
            'ai_flagged': 0,
            'manual_flagged': 0,
            'total_flagged': 0,
            'resolved_today': 0
        }

@app.route('/admin/api/mark_resolved/post/<post_id>', methods=['POST'])
def mark_post_resolved(post_id):
    """Mark a flagged post as resolved"""
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return jsonify({'ok': False, 'error': 'Admin access required'}), 403

    try:
        # Update the post
        result = peersupportposts_col.update_one(
            {'_id': ObjectId(post_id)},
            {
                '$set': {
                    'resolved': True,
                    'resolved_at': datetime.utcnow(),
                    'resolved_by': session.get('user_id')
                }
            }
        )

        if result.modified_count > 0:
            print(f"Post {post_id} marked as resolved by admin {session.get('user_id')}")
            return jsonify({'ok': True, 'message': 'Post marked as resolved'})
        else:
            return jsonify({'ok': False, 'error': 'Post not found'}), 404

    except Exception as e:
        print(f"Error marking post {post_id} as resolved: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to mark post as resolved'}), 500

@app.route('/admin/api/bulk_action', methods=['POST'])
def bulk_action():
    """Perform bulk actions on multiple flagged posts"""
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return jsonify({'ok': False, 'error': 'Admin access required'}), 403

    try:
        data = request.get_json()
        action = data.get('action')  # unflag, delete, resolve
        post_ids = data.get('post_ids', [])

        if not action or not post_ids:
            return jsonify({'ok': False, 'error': 'Missing action or post IDs'}), 400

        # Convert string IDs to ObjectIds
        object_ids = [ObjectId(pid) for pid in post_ids]

        if action == 'unflag':
            result = peersupportposts_col.update_many(
                {'_id': {'$in': object_ids}},
                {
                    '$unset': {
                        'flagged': '',
                        'ai_flagged': '',
                        'flag_categories': '',
                        'flag_reason': ''
                    },
                    '$set': {
                        'unflagged_at': datetime.utcnow(),
                        'unflagged_by': session.get('user_id')
                    }
                }
            )
            message = f"Unflagged {result.modified_count} posts"

        elif action == 'delete':
            result = peersupportposts_col.update_many(
                {'_id': {'$in': object_ids}},
                {
                    '$set': {
                        'is_deleted': True,
                        'deleted_at': datetime.utcnow(),
                        'deleted_by': session.get('user_id')
                    }
                }
            )
            message = f"Deleted {result.modified_count} posts"

        elif action == 'resolve':
            result = peersupportposts_col.update_many(
                {'_id': {'$in': object_ids}},
                {
                    '$set': {
                        'resolved': True,
                        'resolved_at': datetime.utcnow(),
                        'resolved_by': session.get('user_id')
                    }
                }
            )
            message = f"Resolved {result.modified_count} posts"

        else:
            return jsonify({'ok': False, 'error': 'Invalid action'}), 400

        print(f"Bulk action {action} performed on {len(post_ids)} posts by admin {session.get('user_id')}")

        return jsonify({
            'ok': True,
            'message': message,
            'affected_count': result.modified_count
        })

    except Exception as e:
        print(f"Error performing bulk action: {str(e)}")
        return jsonify({'ok': False, 'error': 'Failed to perform bulk action'}), 500

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
        "timestamp": datetime.now()
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
    visits = list(db.page_views.find().sort("timestamp", -1))
    visits=str(visits)


    return render_template(
        "admin_dashboard.html",
        username=session["username"],
        stats=stats,    
        users=users,
        crisis_logs=logs,
        visits=visits
    )
@app.route("/admin/visits_data")
def visits_data():
    total_visits = db.page_views.count_documents({"page": "dashboard"})
    visits_by_date = list(db.page_views.aggregate([
        { "$match": { "page": "dashboard" } },
        { "$group": {
            "_id": { "$dateToString": { "format": "%Y-%m-%d", "date": "$timestamp" } },
            "count": { "$sum": 1 }
        }},
        { "$sort": { "_id": 1 } }
    ]))

    return jsonify({
        "total_visits": total_visits,
        "visits_by_date": visits_by_date
    })



@app.route("/admin/users", methods=["GET", "POST"])
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

@app.route("/admin/flagged_posts", methods=["GET", "POST"])
def admin_flagged_posts():
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
    return render_template("admin_flagged_posts.html", posts=posts)

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
    print(logs)
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
    
@app.route("/admin/mood_trends", methods=["GET"])
def mood_trends():
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403

    # Map moods to numeric values for average calculation
    mood_map = {
        "Happy": 4,
        "Calm": 3,
        "Void": 2,
        "Sad": 1,
        "Angry": 0
    }

    # Aggregate counts per mood per day
    pipeline = [
        {
            "$group": {
                "_id": {
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$datetime"}},
                    "mood": "$mood"
                },
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"_id.date": 1}}
    ]

    results = list(moodtracking_col.aggregate(pipeline))

    # Reshape into { date: {mood: count, ...}, ... }
    mood_data = {}
    for r in results:
        date = r["_id"]["date"]
        mood = r["_id"]["mood"]
        count = r["count"]
        if date not in mood_data:
            mood_data[date] = {}
        mood_data[date][mood] = count


    dates = sorted(mood_data.keys())
    moods = sorted(mood_map.keys(), key=lambda m: -mood_map[m])  # keep consistent order

    distribution = [
        [mood_data[date].get(m, 0) for m in moods]
        for date in dates
    ]

    averages = [
        round(
            sum((mood_map.get(m, 0) * mood_data[date].get(m, 0)) for m in moods) 
            / max(sum(mood_data[date].values()), 1), 2
        )
        for date in dates
    ]

    data = {
        "dates": dates,
        "moods": moods,
        "distribution": distribution,
        "averages": averages
    }
    return jsonify(data), 200

@app.route("/admin/api/stats", methods=["GET"])
def admin_api_stats():
    """Return KPI statistics for admin dashboard"""
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    
    try:
        # Calculate active users (users who logged in within last 30 days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        # For active users, you might want to track login times in users collection
        # For now, we'll use users with recent mood entries or journal entries as proxy
        recent_mood_users = moodtracking_col.distinct("user_id", 
            {"datetime": {"$gte": thirty_days_ago}})
        recent_journal_users = journals_col.distinct("user_id", 
            {"datetime": {"$gte": thirty_days_ago}})
        
        active_users = len(set(recent_mood_users + recent_journal_users))
        
        # New users this month
        first_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_monthly_users = users_col.count_documents({
            "date_joined": {"$gte": first_of_month},
            "role": {"$ne": "admin"}
        })
        
        # Count therapists
        therapists_count = therapists_col.count_documents({})
        
        # Count volunteers (studentvol role)
        volunteers_count = users_col.count_documents({"role": "studentvol"})
        
        # Count proctors
        proctors_count = proctors_col.count_documents({})
        
        # Calculate bounce rate (simplified version)
        # Bounce rate = users with only 1 page view / total users with page views
        total_page_views = page_views_col.count_documents({})
        if total_page_views > 0:
            # Users who visited only once
            single_visit_users = len(list(page_views_col.aggregate([
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                {"$match": {"count": 1}}
            ])))
            
            total_unique_visitors = len(page_views_col.distinct("user_id")) or 1
            bounce_rate_percent = round((single_visit_users / total_unique_visitors) * 100)
        else:
            bounce_rate_percent = 0
        
        kpis = {
            "active_users": active_users,
            "new_monthly_users": new_monthly_users,
            "therapists": therapists_count,
            "volunteers": volunteers_count,
            "proctors": proctors_count,
            "bounce_rate_percent": bounce_rate_percent
        }
        
        return jsonify({"ok": True, "kpis": kpis}), 200
        
    except Exception as e:
        print(f"Error calculating admin stats: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    
    
@app.route("/admin/api/daily_hits", methods=["GET"])
def admin_daily_hits():
    """Return daily page hits for the last 30 days"""
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        # Get last 30 days of page views
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        pipeline = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        results = list(page_views_col.aggregate(pipeline))
        
        # Create array of last 30 days
        dates = []
        counts = []
        
        for i in range(30):
            date = (datetime.now() - timedelta(days=29-i)).strftime("%Y-%m-%d")
            dates.append(date)
            
            # Find count for this date
            count = 0
            for result in results:
                if result["_id"] == date:
                    count = result["count"]
                    break
            counts.append(count)
        
        return jsonify({
            "labels": [datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d") for d in dates],
            "counts": counts
        }), 200
        
    except Exception as e:
        print(f"Error getting daily hits: {e}")
        return jsonify({"labels": [], "counts": []}), 500

@app.route("/admin/api/mood_trend", methods=["GET"])
def admin_mood_trend():
    """Return mood trend data for the last 30 days"""
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        # Mood scoring system
        mood_scores = {
            "Very Happy": 8,
            "Feeling Blessed": 7,
            "Happy": 6,
            "Mind Blown": 5,
            "Frustrated": 3,
            "Sad": 2,
            "Angry": 1,
            "Crying": 0
        }
        
        pipeline = [
            {"$match": {"datetime": {"$gte": thirty_days_ago}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$datetime"}},
                "moods": {"$push": "$mood"}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        results = list(moodtracking_col.aggregate(pipeline))
        
        # Calculate daily averages
        dates = []
        averages = []
        
        for i in range(30):
            date = (datetime.now() - timedelta(days=29-i)).strftime("%Y-%m-%d")
            dates.append(date)
            
            # Find moods for this date
            daily_moods = []
            for result in results:
                if result["_id"] == date:
                    daily_moods = result["moods"]
                    break
            
            if daily_moods:
                # Calculate average mood score for the day
                scores = [mood_scores.get(mood, 4) for mood in daily_moods]  # default to 4 if unknown
                avg = sum(scores) / len(scores)
                averages.append(round(avg, 1))
            else:
                averages.append(0)
        
        return jsonify({
            "labels": [datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d") for d in dates],
            "avgs": averages
        }), 200
        
    except Exception as e:
        print(f"Error getting mood trend: {e}")
        return jsonify({"labels": [], "avgs": []}), 500

@app.route("/track_page", methods=["POST"])
def track_page():
    """Track page visits with user information"""
    data = request.get_json() or {}
    
    # Add user info if available
    user_id = session.get("user_id")
    username = session.get("username")
    
    page_view = {
        "page": data.get("page", "unknown"),
        "user_id": user_id,
        "username": username,
        "timestamp": datetime.now(),
        "duration": data.get("duration", 0),  # time spent on page
        "user_agent": request.headers.get("User-Agent", ""),
        "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr)
    }
    
    page_views_col.insert_one(page_view)
    return jsonify({"status": "success"}), 200

@app.route("/admin/api/average_scores", methods=["GET"])
def admin_average_scores():
    try:
        # Get all assessment records
        cursor = assess_col.find({})
        
        gad_scores = []
        phq_scores = []
        ghq_likert_scores = []
        ghq_bimodal_scores = []
        test_type_counts = {}
        
        for doc in cursor:
            # Count test types
            test_type = doc.get("test_type", "COMBINED")
            test_type_counts[test_type] = test_type_counts.get(test_type, 0) + 1
            
            # Collect scores
            gad_total = doc.get("gadTotal", 0)
            phq_total = doc.get("phqTotal", 0)
            ghq_likert = doc.get("ghqLikertTotal", 0)
            ghq_bimodal = doc.get("ghqBimodalTotal", 0)
            
            if gad_total > 0:
                gad_scores.append(gad_total)
            if phq_total > 0:
                phq_scores.append(phq_total)
            if ghq_likert > 0:
                ghq_likert_scores.append(ghq_likert)
            if ghq_bimodal > 0:
                ghq_bimodal_scores.append(ghq_bimodal)
        
        # Calculate averages
        avg_gad = round(sum(gad_scores) / len(gad_scores), 2) if gad_scores else 0
        avg_phq = round(sum(phq_scores) / len(phq_scores), 2) if phq_scores else 0
        avg_ghq_likert = round(sum(ghq_likert_scores) / len(ghq_likert_scores), 2) if ghq_likert_scores else 0
        avg_ghq_bimodal = round(sum(ghq_bimodal_scores) / len(ghq_bimodal_scores), 2) if ghq_bimodal_scores else 0
        
        # Calculate severity distributions
        gad_severity_counts = {'Minimal': 0, 'Mild': 0, 'Moderate': 0, 'Severe': 0}
        phq_severity_counts = {'None-Minimal': 0, 'Mild': 0, 'Moderate': 0, 'Moderately severe': 0, 'Severe': 0}
        ghq_severity_counts = {'Normal': 0, 'Mild': 0, 'Moderate': 0, 'Severe': 0}
        
        for score in gad_scores:
            severity = calculate_gad_severity(score)
            gad_severity_counts[severity] += 1
            
        for score in phq_scores:
            severity = calculate_phq_severity(score)
            phq_severity_counts[severity] += 1
            
        for score in ghq_likert_scores:
            severity = calculate_ghq_severity(score)
            ghq_severity_counts[severity] += 1
        
        return jsonify({
            "ok": True,
            "avg_gad": avg_gad,
            "avg_phq": avg_phq,
            "avg_ghq_likert": avg_ghq_likert,
            "avg_ghq_bimodal": avg_ghq_bimodal,
            "total_assessments": len(gad_scores + phq_scores + ghq_likert_scores),
            "test_type_distribution": test_type_counts,
            "gad_severity_distribution": gad_severity_counts,
            "phq_severity_distribution": phq_severity_counts,
            "ghq_severity_distribution": ghq_severity_counts
        })
        
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# --- Debug ---
@app.route("/debug/all_collections")
def debug_all_collections():
    if "user_id" not in session or session["role"] != "admin":
        return jsonify({"error": "admin access required"}), 403
    
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
    

# @app.route('/assessment')
# def assessment():
#     if not session.get('username'):
#         # redirect to login if you require auth
#         return redirect(url_for('login'))
#     # render the template; session values are available via session[...] inside template
#     return render_template('assessment.html')

# --- Assessment Scoring Helper Functions ---
def calculate_ghq_scores(ghq_answers):
    """
    Calculate GHQ-12 scores using both Likert and bimodal methods.
    GHQ questions have different orientations (positive/negative).
    """
    # GHQ-12 question orientations (based on the frontend questions)
    # Positive items: 0, 2, 3, 6, 7, 11 (indices in GHQ subset)
    # Negative items: 1, 4, 5, 8, 9, 10
    positive_indices = [0, 2, 3, 6, 7, 11]
    
    likert_total = sum(ghq_answers)
    
    # Bimodal scoring: 0-1 = 0, 2-3 = 1
    bimodal_total = 0
    for i, score in enumerate(ghq_answers):
        if i in positive_indices:
            # For positive items: 0,1 = 0; 2,3 = 1
            bimodal_total += 1 if score >= 2 else 0
        else:
            # For negative items: 0,1 = 0; 2,3 = 1  
            bimodal_total += 1 if score >= 2 else 0
    
    return likert_total, bimodal_total

def calculate_gad_severity(total):
    """Calculate GAD-7 severity level"""
    if total >= 15:
        return 'Severe'
    elif total >= 10:
        return 'Moderate'
    elif total >= 5:
        return 'Mild'
    else:
        return 'Minimal'

def calculate_phq_severity(total):
    """Calculate PHQ-9 severity level"""
    if total >= 20:
        return 'Severe'
    elif total >= 15:
        return 'Moderately severe'
    elif total >= 10:
        return 'Moderate'
    elif total >= 5:
        return 'Mild'
    else:
        return 'None-Minimal'

def calculate_ghq_severity(likert_total):
    """Calculate GHQ-12 severity level based on Likert scoring"""
    if likert_total >= 20:
        return 'Severe'
    elif likert_total >= 15:
        return 'Moderate'
    elif likert_total >= 10:
        return 'Mild'
    else:
        return 'Normal'

@app.route("/api/submit", methods=["POST"])
def api_submit():
    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers")
    test_type = payload.get("testType", "COMBINED")

    # Validate answers based on test type
    if not isinstance(answers, list):
        return jsonify({"ok": False, "error": "Answers must be an array"}), 400

    # Determine expected length based on test type
    expected_lengths = {
        "GAD": 7,
        "PHQ": 9, 
        "GHQ": 12,
        "COMBINED": 28
    }
    
    expected_length = expected_lengths.get(test_type, 28)
    if len(answers) != expected_length:
        return jsonify({
            "ok": False, 
            "error": f"Invalid answers array; expected {expected_length} items for {test_type} test"
        }), 400

    # normalize answers to ints (null -> 0)
    try:
        answers_norm = [int(x) if x is not None else 0 for x in answers]
    except Exception:
        return jsonify({"ok": False, "error": "Answers must be numbers or null"}), 400

    # Initialize result variables
    gad_total = 0
    phq_total = 0
    ghq_likert_total = 0
    ghq_bimodal_total = 0
    gad_sev = "Minimal"
    phq_sev = "None-Minimal"
    ghq_sev = "Normal"

    # Calculate scores based on test type
    if test_type == "COMBINED":
        # Combined: GAD-7 (0-6), PHQ-9 (7-15), GHQ-12 (16-27)
        gad_scores = answers_norm[:7]
        phq_scores = answers_norm[7:16]
        ghq_scores = answers_norm[16:28]
        
        gad_total = sum(gad_scores)
        phq_total = sum(phq_scores)
        ghq_likert_total, ghq_bimodal_total = calculate_ghq_scores(ghq_scores)
        
    elif test_type == "GAD":
        # GAD-7 only
        gad_scores = answers_norm[:7]
        gad_total = sum(gad_scores)
        
    elif test_type == "PHQ":
        # PHQ-9 only
        phq_scores = answers_norm[:9]
        phq_total = sum(phq_scores)
        
    elif test_type == "GHQ":
        # GHQ-12 only
        ghq_scores = answers_norm[:12]
        ghq_likert_total, ghq_bimodal_total = calculate_ghq_scores(ghq_scores)

    # Calculate severity levels
    gad_sev = calculate_gad_severity(gad_total)
    phq_sev = calculate_phq_severity(phq_total)
    ghq_sev = calculate_ghq_severity(ghq_likert_total)

    # associate user: prefer session user_id for security
    user_id = session.get('user_id') or payload.get('user_id') or 'anon'

    # Build document for database
    doc = {
        "user_id": user_id,
        "test_type": test_type,
        "answers": answers_norm,
        "timestamp": datetime.utcnow()
    }

    # Add scores only if they were calculated
    if gad_total > 0 or test_type in ["GAD", "COMBINED"]:
        doc.update({
            "gadTotal": int(gad_total),
            "gadSeverity": gad_sev
        })
    
    if phq_total > 0 or test_type in ["PHQ", "COMBINED"]:
        doc.update({
            "phqTotal": int(phq_total),
            "phqSeverity": phq_sev
        })
    
    if ghq_likert_total > 0 or test_type in ["GHQ", "COMBINED"]:
        doc.update({
            "ghqLikertTotal": int(ghq_likert_total),
            "ghqBimodalTotal": int(ghq_bimodal_total),
            "ghqSeverity": ghq_sev
        })

    # Insert into database
    res = assess_col.insert_one(doc)
    
    # Build response
    response = {
        "ok": True,
        "id": str(res.inserted_id),
        "testType": test_type,
        "timestamp": doc["timestamp"].isoformat() + "Z"
    }
    
    # Add scores to response only if they were calculated
    if "gadTotal" in doc:
        response.update({
            "gadTotal": doc["gadTotal"],
            "gadSeverity": doc["gadSeverity"]
        })
    
    if "phqTotal" in doc:
        response.update({
            "phqTotal": doc["phqTotal"],
            "phqSeverity": doc["phqSeverity"]
        })
    
    if "ghqLikertTotal" in doc:
        response.update({
            "ghqLikertTotal": doc["ghqLikertTotal"],
            "ghqBimodalTotal": doc["ghqBimodalTotal"],
            "ghqSeverity": doc["ghqSeverity"]
        })

    return jsonify(response), 200

@app.route("/api/scores", methods=["GET"])
def api_scores():
    # prefer logged-in session user
    uid = session.get('user_id') or request.args.get('user_id')
    test_type = request.args.get('test_type')  # Optional filter by test type
    
    query = {}
    if uid:
        query["user_id"] = uid
    if test_type:
        query["test_type"] = test_type

    cursor = assess_col.find(query).sort("timestamp", -1).limit(100)
    out = []
    for d in cursor:
        result = {
            "id": str(d.get("_id")),
            "user_id": d.get("user_id"),
            "test_type": d.get("test_type", "COMBINED"),
            "timestamp": d.get("timestamp").isoformat() + "Z" if d.get("timestamp") else None
        }
        
        # Add GAD scores if present
        if "gadTotal" in d:
            result.update({
                "gadTotal": int(d.get("gadTotal", 0)),
                "gadSeverity": d.get("gadSeverity")
            })
        
        # Add PHQ scores if present
        if "phqTotal" in d:
            result.update({
                "phqTotal": int(d.get("phqTotal", 0)),
                "phqSeverity": d.get("phqSeverity")
            })
        
        # Add GHQ scores if present
        if "ghqLikertTotal" in d:
            result.update({
                "ghqLikertTotal": int(d.get("ghqLikertTotal", 0)),
                "ghqBimodalTotal": int(d.get("ghqBimodalTotal", 0)),
                "ghqSeverity": d.get("ghqSeverity")
            })
        
        out.append(result)
    
    return jsonify(out), 200

@app.route("/api/latest_scores", methods=["GET"])
def api_latest_scores():
    """Get the most recent assessment scores for a user"""
    uid = session.get('user_id') or request.args.get('user_id')
    if not uid:
        return jsonify({"error": "User ID required"}), 400
    
    # Get the most recent assessment for this user
    latest_assessment = assess_col.find_one(
        {"user_id": uid}, 
        sort=[("timestamp", -1)]
    )
    
    if not latest_assessment:
        return jsonify({"error": "No assessments found"}), 404
    
    result = {
        "user_id": latest_assessment.get("user_id"),
        "test_type": latest_assessment.get("test_type", "COMBINED"),
        "timestamp": latest_assessment.get("timestamp").isoformat() + "Z" if latest_assessment.get("timestamp") else None
    }
    
    # Add available scores
    if "gadTotal" in latest_assessment:
        result.update({
            "gadTotal": int(latest_assessment.get("gadTotal", 0)),
            "gadSeverity": latest_assessment.get("gadSeverity")
        })
    
    if "phqTotal" in latest_assessment:
        result.update({
            "phqTotal": int(latest_assessment.get("phqTotal", 0)),
            "phqSeverity": latest_assessment.get("phqSeverity")
        })
    
    if "ghqLikertTotal" in latest_assessment:
        result.update({
            "ghqLikertTotal": int(latest_assessment.get("ghqLikertTotal", 0)),
            "ghqBimodalTotal": int(latest_assessment.get("ghqBimodalTotal", 0)),
            "ghqSeverity": latest_assessment.get("ghqSeverity")
        })
    
    return jsonify(result), 200

@app.route("/api/download_report", methods=["GET"])
def api_download_report():
    """Download assessment report as JSON"""
    uid = session.get('user_id') or request.args.get('user_id')
    assessment_id = request.args.get('assessment_id')
    
    if not uid:
        return jsonify({"error": "User ID required"}), 400
    
    query = {"user_id": uid}
    if assessment_id:
        try:
            query["_id"] = ObjectId(assessment_id)
        except:
            return jsonify({"error": "Invalid assessment ID"}), 400
    
    assessment = assess_col.find_one(query)
    if not assessment:
        return jsonify({"error": "Assessment not found"}), 404
    
    # Convert ObjectId to string for JSON serialization
    assessment["_id"] = str(assessment["_id"])
    if "timestamp" in assessment and assessment["timestamp"]:
        assessment["timestamp"] = assessment["timestamp"].isoformat() + "Z"
    
    return jsonify(assessment), 200

@app.route("/api/assessment_stats", methods=["GET"])
def api_assessment_stats():
    """Get assessment statistics for a user"""
    uid = session.get('user_id') or request.args.get('user_id')
    if not uid:
        return jsonify({"error": "User ID required"}), 400
    
    try:
        # Get all assessments for this user
        cursor = assess_col.find({"user_id": uid}).sort("timestamp", -1)
        assessments = list(cursor)
        
        if not assessments:
            return jsonify({
                "total_assessments": 0,
                "latest_assessment": None,
                "test_types_taken": [],
                "score_trends": {}
            })
        
        # Calculate statistics
        test_types = list(set([a.get("test_type", "COMBINED") for a in assessments]))
        
        # Get latest assessment
        latest = assessments[0]
        latest_data = {
            "test_type": latest.get("test_type", "COMBINED"),
            "timestamp": latest.get("timestamp").isoformat() + "Z" if latest.get("timestamp") else None
        }
        
        # Add scores from latest assessment
        if "gadTotal" in latest:
            latest_data.update({
                "gadTotal": latest.get("gadTotal"),
                "gadSeverity": latest.get("gadSeverity")
            })
        if "phqTotal" in latest:
            latest_data.update({
                "phqTotal": latest.get("phqTotal"),
                "phqSeverity": latest.get("phqSeverity")
            })
        if "ghqLikertTotal" in latest:
            latest_data.update({
                "ghqLikertTotal": latest.get("ghqLikertTotal"),
                "ghqBimodalTotal": latest.get("ghqBimodalTotal"),
                "ghqSeverity": latest.get("ghqSeverity")
            })
        
        # Calculate score trends (last 10 assessments)
        recent_assessments = assessments[:10]
        score_trends = {
            "gad": [a.get("gadTotal", 0) for a in recent_assessments if "gadTotal" in a],
            "phq": [a.get("phqTotal", 0) for a in recent_assessments if "phqTotal" in a],
            "ghq_likert": [a.get("ghqLikertTotal", 0) for a in recent_assessments if "ghqLikertTotal" in a],
            "ghq_bimodal": [a.get("ghqBimodalTotal", 0) for a in recent_assessments if "ghqBimodalTotal" in a]
        }
        
        return jsonify({
            "total_assessments": len(assessments),
            "latest_assessment": latest_data,
            "test_types_taken": test_types,
            "score_trends": score_trends
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/assessment')
def assessment():
    if not session.get('username'):
        # redirect to login if you require auth
        return redirect(url_for('login'))
    # render the template; session values are available via session[...] inside template
    return render_template('assessment.html')


# crisis email message call------------------------------------------ 
SENDER = os.environ.get("CRISIS_EMAIL")
APP_PWD = os.environ.get("CRISIS_APP_PASSWORD")
RECEIVER = os.environ.get("CRISIS_RECEIVER")

executor = ThreadPoolExecutor(max_workers=4)
logging.basicConfig(level=logging.DEBUG)
CORS(app)   # allow cross-origin calls during dev

@app.route("/send_email", methods=["POST"])
def send_email():
    SENDER = os.environ.get("CRISIS_EMAIL")
    APP_PWD = os.environ.get("CRISIS_APP_PASSWORD")
    RECEIVER = os.environ.get("CRISIS_RECEIVER")

    if not (SENDER and APP_PWD and RECEIVER):
        return jsonify({"ok": False, "error": "Missing env vars (CRISIS_EMAIL / CRISIS_APP_PASSWORD / CRISIS_RECEIVER)"}), 500

    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = RECEIVER
    msg["Subject"] = "🚨 Crisis Alert"
    msg.set_content("Crisis button triggered in dashboard.")

    # Attempt 1: SSL on 465
    try:
        logging.info("Trying SMTP_SSL smtp.gmail.com:465")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(SENDER, APP_PWD)
            smtp.send_message(msg)
        logging.info("Email sent via 465")
        return jsonify({"ok": True, "method": "ssl465"}), 200
    except Exception as e465:
        logging.warning("465 attempt failed: %s", repr(e465))

    # Attempt 2: STARTTLS on 587
    try:
        logging.info("Trying SMTP STARTTLS smtp.gmail.com:587")
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(SENDER, APP_PWD)
            smtp.send_message(msg)
        logging.info("Email sent via 587")
        return jsonify({"ok": True, "method": "starttls587"}), 200
    except Exception as e587:
        logging.exception("587 attempt failed")

    # Both attempts failed — return both errors
    return jsonify({
        "ok": False,
        "error": "Both connection attempts failed",
        "details_465": repr(e465),
        "details_587": repr(e587)
    }), 500


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



# Add dependencies:
# pip install google-cloud-speech flask tempfile


# Make sure GOOGLE_APPLICATION_CREDENTIALS env var is set to the JSON key path.
# configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transcribe")

def ffmpeg_installed():
    try:
        subprocess.check_output(["ffmpeg", "-version"])
        return True
    except Exception:
        return False

def convert_to_wav(input_path, output_path, sample_rate=16000):
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",                 # mono
        "-ar", str(sample_rate),    # sample rate
        "-sample_fmt", "s16",       # 16-bit
        output_path
    ]
    logger.info("Running ffmpeg command: %s", " ".join(cmd))
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

@app.route("/transcribe", methods=["POST"])
def transcribe_audio():
    """
    Accepts multipart form-data with file field 'audio'.
    Optional form field: 'languageCode' (e.g. 'en-US' or 'hi-IN').
    Returns JSON with either {"transcript": "..."} or {"error": "..."} and proper status code.
    """
    try:
        # Basic checks
        if 'audio' not in request.files:
            logger.warning("No 'audio' in request.files")
            return jsonify({"error": "No audio file uploaded. Send multipart/form-data with field 'audio'."}), 400

        audio_file = request.files['audio']
        logger.info("Received file: filename=%s content_type=%s size=%s", audio_file.filename, audio_file.content_type, request.content_length)

        # Save incoming file to temp
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "input_audio")
            audio_file.save(src_path)
            logger.info("Saved incoming audio to %s", src_path)

            # Optional: check file size (in bytes) and reject huge files
            max_bytes = 10 * 1024 * 1024  # 10 MB
            file_size = os.path.getsize(src_path)
            logger.info("Uploaded file size: %d bytes", file_size)
            if file_size > max_bytes:
                return jsonify({"error": f"Uploaded audio too large ({file_size} bytes). Max allowed {max_bytes} bytes."}), 413

            # Make sure ffmpeg exists
            if not ffmpeg_installed():
                logger.error("ffmpeg not found on server PATH")
                return jsonify({"error": "Server misconfiguration: ffmpeg not installed on server."}), 500

            wav_path = os.path.join(tmpdir, "converted.wav")
            try:
                convert_to_wav(src_path, wav_path, sample_rate=16000)
            except subprocess.CalledProcessError as e:
                logger.exception("ffmpeg conversion failed")
                return jsonify({"error": "Audio conversion failed (ffmpeg error). Are you sending a valid audio blob?"}), 500

            # read converted wav
            with open(wav_path, "rb") as f:
                wav_bytes = f.read()

            # Prepare Google Speech client
            try:
                client = speech.SpeechClient()
            except Exception as e:
                logger.exception("Failed to initialize Google Speech client")
                return jsonify({"error": "Server misconfiguration: Google Speech client init failed. Check GOOGLE_APPLICATION_CREDENTIALS."}), 500

            language_code = request.form.get('languageCode') or request.headers.get('X-Language-Code') or "en-US"
            logger.info("Using language code: %s", language_code)

            audio = speech.RecognitionAudio(content=wav_bytes)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language_code,
                enable_automatic_punctuation=True,
            )

            try:
                # synchronous recognize (good for short audio < 60s)
                response = client.recognize(config=config, audio=audio)
            except Exception as e:
                logger.exception("Google Speech API error")
                return jsonify({"error": f"Speech API error: {str(e)}"}), 500

            # Build transcript
            transcripts = []
            for result in response.results:
                transcripts.append(result.alternatives[0].transcript)
            transcript_text = " ".join(transcripts).strip()

            logger.info("Transcription result: %s", transcript_text)
            return jsonify({"transcript": transcript_text}), 200

    except Exception as e:
        logger.exception("Unhandled exception in /transcribe")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


# --- Run App ---
if __name__ == "__main__":
    app.run(debug=True)