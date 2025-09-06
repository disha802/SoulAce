from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import json
import os
from datetime import datetime
import csv

app = Flask(__name__)
app.secret_key = "secretkey123"

CSV_FILE = "moods.csv"

# Load users from JSON file
USERS_FILE = "users.json"
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r") as f:
        users = json.load(f)
else:
    users = {
        "user1": "password123",
        "admin": "adminpass"
    }
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Date", "Time", "Mood"])

JOURNAL_FILE = "journal.json"

# Load journal entries
if os.path.exists(JOURNAL_FILE):
    with open(JOURNAL_FILE, "r") as f:
        journal_entries = json.load(f)
else:
    journal_entries = []
    with open(JOURNAL_FILE, "w") as f:
        json.dump(journal_entries, f)


@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username in users and users[username] == password:
            session["username"] = username
            if username == "admin":
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
        if username in users:
            flash("User already exists", "error")
        else:
            users[username] = password
            # Save to JSON
            with open(USERS_FILE, "w") as f:
                json.dump(users, f)
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", username=session["username"])

@app.route("/save_mood", methods=["POST"])
def save_mood():
    data = request.get_json()
    mood = data.get("mood")
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M:%S")

    with open(CSV_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([date, time, mood])

    return jsonify({"message": f"Mood set to {mood}!"})

@app.route("/download_moods", methods=["GET"])
def download_csv():
    return send_file(CSV_FILE, as_attachment=True)

@app.route("/resources")
def resources():
    return render_template("resources.html",  username=session["username"])


@app.route("/journal", methods=["GET", "POST"])
def journal():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        content = request.form.get("content")
        if content.strip():
            entry = {
                "id": len(journal_entries) + 1,
                "username": session["username"],
                "content": content,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S")
            }
            journal_entries.append(entry)

            with open(JOURNAL_FILE, "w") as f:
                json.dump(journal_entries, f, indent=2)

    return render_template("journal.html", entries=journal_entries, username=session["username"])

@app.route("/add_journal", methods=["POST"])
def add_journal():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    title = data.get("title", "").strip()   # <-- added this
    content = data.get("content", "").strip()

    if not title or not content:
        return jsonify({"error": "Empty title or content"}), 400

    entry = {
        "id": len(journal_entries) + 1,
        "username": session["username"],
        "title": title,                    # <-- save title
        "content": content,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S")
    }
    journal_entries.append(entry)

    with open(JOURNAL_FILE, "w") as f:
        json.dump(journal_entries, f, indent=2)

    return jsonify({"message": "Entry added!", "entry": entry}), 201

@app.route("/get_journals/<username>", methods=["GET"])
def get_journals(username):
    user_entries = [e for e in journal_entries if e["username"] == username]
    return jsonify(user_entries)


@app.route("/delete_journal/<int:entry_id>", methods=["DELETE"])
def delete_journal(entry_id):
    global journal_entries
    journal_entries = [e for e in journal_entries if e["id"] != entry_id]
    with open(JOURNAL_FILE, "w") as f:
        json.dump(journal_entries, f, indent=2)
    return jsonify({"message": "Entry deleted"})



@app.route("/admin")
def admin_dashboard():
    if "username" not in session or session["username"] != "admin":
        return redirect(url_for("login"))
    return render_template("admin_dashboard.html", username=session["username"])

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for("login"))

@app.route("/ai-chat")
def chat():
    pass
    

if __name__ == "__main__":
    app.run(debug=True)
