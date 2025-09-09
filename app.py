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
crisis_col = db["crisis_logs"]

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

def create_default_Admin():
    """Create default Admin user if doesn't exist"""
    Admin_exists = users_col.find_one({"role": "Admin"})
    if not Admin_exists:
        Admin_user = {
            "user_id": get_next_id(users_col, "user_id"),
            "username": "Admin",
            "password_hash": generate_password_hash("adminpass"),
            "role": "Admin",
            "date_joined": datetime.now()
        }
        users_col.insert_one(Admin_user)
        print("✅ Default Admin user created")

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

def check(content: str) -> bool:
    """
    AI moderation stub.
    Returns True if content is inappropriate (flagged), False otherwise.
    Replace later with actual AI model.
    """
    return False

# --- Helper Functions for Admin ---
def get_all_users():
    """Fetch all users except admins"""
    users = list(users_col.find({"role": {"$ne": "Admin"}}))  # exclude admins
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

from bson.objectid import ObjectId
from datetime import datetime

def get_crisis_logs():
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return "Unauthorized", 403

    logs = list(db["crisis"].find({}))
    formatted_logs = []
    for log in logs:
        formatted_logs.append({
            "id": str(log.get("_id", ObjectId())),  # ensure an id is available
            "username": log.get("username", ""),
            "ip_address": log.get("ip_address", ""),
            "timestamp": log.get("timestamp").strftime("%Y-%m-%d %H:%M:%S") if isinstance(log.get("timestamp"), datetime) else str(log.get("timestamp"))
        })

    return jsonify(formatted_logs), 200



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
            
            if user["role"] == "Admin":
                return redirect(url_for("Admin_dashboard"))
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
        post["username"] = "Anonymous" if post.get("is_anonymous") else user.get("username", "Unknown")
        post["isStudentVol"] = (user and user.get("role", "").lower() == "studentvol")

        for reply in post.get("replies", []):
            reply["_id"] = str(reply["_id"])
            reply_user = users_col.find_one({"user_id": reply["user_id"]})
            reply["isStudentVol"] = (reply_user and reply_user.get("role", "").lower() == "studentvol")

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

    user_role = session.get("role", "User").lower()
    flagged = check(content)

    post = {
        "user_id": session["user_id"],
        "datetime": datetime.now(),
        "content": content,
        "is_anonymous": bool(is_anonymous),
        "likes": [],
        "dislikes": [],
        "replies": [],
        "flagged": flagged,
        "isStudentVol": (user_role == "studentvol")
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

    reply = {
        "_id": ObjectId(),
        "user_id": session["user_id"],
        "username": session["username"],
        "datetime": datetime.now(),
        "content": reply_content,
        "flagged": check(reply_content),
        "likes": [],
        "dislikes": [],
        "isStudentVol": (session.get("role", "").lower() == "studentvol")
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
    action = data.get("action")  # "like" or "dislike"
    user_id = session["user_id"]

    post = peersupportposts_col.find_one({"_id": ObjectId(post_id)})
    if not post:
        return jsonify({"error": "Post not found"}), 404

    likes = post.get("likes", [])
    dislikes = post.get("dislikes", [])

    # Toggle logic
    if action == "like":
        if user_id in likes:
            likes.remove(user_id)  # undo like
        else:
            likes.append(user_id)
            if user_id in dislikes:
                dislikes.remove(user_id)  # can't like and dislike
    elif action == "dislike":
        if user_id in dislikes:
            dislikes.remove(user_id)  # undo dislike
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


@app.route("/moderate/unflag/<post_id>", methods=["POST"])
def unflag_post(post_id):
    if "user_id" not in session or session["role"] != "Admin":
        return jsonify({"error": "Admin access required"}), 403
    peersupportposts_col.update_one({"_id": ObjectId(post_id)}, {"$set": {"flagged": False}})
    return jsonify({"message": "Post unflagged"})

@app.route("/moderate/delete/<post_id>", methods=["DELETE"])
def delete_post(post_id):
    if "user_id" not in session or session["role"] != "Admin":
        return jsonify({"error": "Admin access required"}), 403
    peersupportposts_col.delete_one({"_id": ObjectId(post_id)})
    return jsonify({"message": "Post deleted"})

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


#---Admin Routes---
@app.route("/Admin", methods=["GET", "POST"])
def Admin_dashboard():
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return redirect(url_for("login"))

    # Handle role updates
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

    users = get_all_users()  # fetch all non-admin users

    logs = list(db["crisis"].find({}))
    formatted_logs = []
    for log in logs:
        formatted_logs.append({
            "id": str(log.get("_id")),  
            "username": log.get("username", ""),
            "ip_address": log.get("ip_address", ""),
            "timestamp": log.get("timestamp").strftime("%Y-%m-%d %H:%M:%S")
            if log.get("timestamp") else ""
        })

    return render_template("Admin_dashboard.html", username=session["username"], stats=stats, users=users, crisis_logs = formatted_logs)


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
    return render_template("Admin_dashboard.html", users=users)

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
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return "Unauthorized", 403

    logs = list(db["crisis"].find({}, {"_id": 0}))
    print (logs)
    return jsonify(logs), 200

@app.route("/resolve_crisis", methods=["POST"])
def resolve_crisis():
    if "user_id" not in session or session.get("role", "").lower() != "admin":
        return "Unauthorized", 403

    log_id = request.form.get("log_id")
    if not log_id:
        return "Missing log_id", 400

    try:
        db["crisis"].delete_one({"_id": ObjectId(log_id)})
    except Exception as e:
        print("Error deleting crisis log:", e)
        return "Invalid log_id", 400

    return redirect(url_for("Admin_dashboard"))

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

# --- Run App ---
if __name__ == "__main__":
    app.run(debug=True)
