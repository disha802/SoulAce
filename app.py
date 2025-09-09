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
    
    # Create default StudentVol user
    stuvol_exists = users_col.find_one({"username": "studentvol"})
    if not stuvol_exists:
        stuvol_user = {
            "user_id": get_next_id(users_col, "user_id"),
            "username": "studentvol",
            "password_hash": generate_password_hash("studentvol"),
            "role": "StudentVol",
            "date_joined": datetime.now()
        }
        users_col.insert_one(stuvol_user)
        print("✅ Default StudentVol user created (username: studentvol, password: studentvol)")

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

# Initialize default data
create_default_admin()
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
            
            if user["role"] == "Admin":
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
                "role": "User",
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
@app.route("/journal")
def journal():
    if "user_id" not in session:
        flash("Please login to access journals", "warning")
        return redirect(url_for("login"))
    return render_template("journal.html", username=session["username"])

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
    if mood not in valid_moods:
        return jsonify({"error": "Invalid mood value"}), 400
    
    mood_entry = {
        "mood_id": get_next_id(moodtracking_col, "mood_id"),
        "user_id": session["user_id"],
        "datetime": datetime.now(),
        "mood": mood
    }
    
    try:
        moodtracking_col.insert_one(mood_entry)
        return jsonify({"message": f"Mood set to {mood}!"})
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

# --- Peer Forum Routes ---
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
            post["isStudentVol"] = (user and user.get("role") == "StudentVol")

        for reply in post.get("replies", []):
            reply["_id"] = str(reply["_id"])
            reply_user = users_col.find_one({"user_id": reply["user_id"]})

            if reply.get("is_deleted"):
                reply["username"] = "Deleted User"
                reply["content"] = "Reply deleted"
            else:
                # Fix the role check to match the actual role value
                reply["isStudentVol"] = (reply_user and reply_user.get("role") == "StudentVol")
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

    user_role = session.get("role", "User")
    
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
        "isStudentVol": (user_role == "StudentVol"),
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
        "isStudentVol": (session.get("role") == "StudentVol"),
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

        # Allow deletion if it's the owner's post OR if user is an Admin OR StudentVol
        if (post_user_id != session_user_id and 
            user_role not in ["Admin", "StudentVol"]):
            return jsonify({"error": "Unauthorized"}), 403

        # Soft delete for owners, hard delete for Admins and StudentVols
        if user_role in ["Admin", "StudentVol"]:
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
            # Allow deletion if owner OR Admin OR StudentVol
            if (str(reply["user_id"]) != str(session["user_id"]) and 
                user_role not in ["Admin", "StudentVol"]):
                return jsonify({"error": "Unauthorized"}), 403

            if user_role in ["Admin", "StudentVol"]:
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


# --- Flag content (StudentVol only) ---
@app.route("/flag_content/<content_type>/<content_id>", methods=["POST"])
def flag_content(content_type, content_id):
    if "user_id" not in session or session.get("role") != "StudentVol":
        return jsonify({"error": "StudentVol access required"}), 403

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


# --- Unflag content (Admin and StudentVol) ---
@app.route("/unflag_content/<content_type>/<content_id>", methods=["POST"])
def unflag_content(content_type, content_id):
    if "user_id" not in session or session.get("role") not in ["Admin", "StudentVol"]:
        return jsonify({"error": "Admin or StudentVol access required"}), 403

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

# --- Admin ---
@app.route("/admin")
def admin_dashboard():
    if "user_id" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
    
    stats = {
        "total_users": users_col.count_documents({"role": "User"}),
        "total_journals": journals_col.count_documents({}),
        "total_appointments": appointments_col.count_documents({}),
        "total_posts": peersupportposts_col.count_documents({})
    }
    
    # Get flagged content for moderation
    flagged_posts = list(peersupportposts_col.find({
        "$or": [{"flagged": True}, {"ai_flagged": True}]
    }).sort("datetime", -1))
    
    for post in flagged_posts:
        post["_id"] = str(post["_id"])
        user = users_col.find_one({"user_id": post["user_id"]})
        post["username"] = user.get("username", "Unknown") if user else "Unknown"
    
    return render_template("admin_dashboard.html", 
                         username=session["username"],
                         stats=stats,
                         flagged_posts=flagged_posts)

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