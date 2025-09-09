import os
import matplotlib.pyplot as plt
from datetime import datetime
from bson.objectid import ObjectId
from flask import current_app

CHART_DIR = "static/charts"
os.makedirs(CHART_DIR, exist_ok=True)

# Mood → Sentiment categories
mood_sentiment_map = {
    "Very Happy": "positive",
    "Feeling Blessed": "positive",
    "Happy": "positive",
    "Mind Blown": "neutral",
    "Frustrated": "negative",
    "Sad": "negative",
    "Angry": "negative",
    "Crying": "negative"
}

def generate_user_chart(user_id, moodtracking_col):
    """Generate sentiment chart for one user."""
    logs = list(moodtracking_col.find({"user_id": user_id}))
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}

    for log in logs:
        mood = log.get("mood")
        category = mood_sentiment_map.get(mood, "neutral")
        sentiments[category] += 1

    labels = list(sentiments.keys())
    values = list(sentiments.values())

    plt.figure(figsize=(6, 4))
    plt.bar(labels, values, color=["green", "blue", "red"])
    plt.title(f"Sentiment Analysis for User {user_id}")
    file_path = os.path.join(CHART_DIR, f"user_{user_id}_sentiment.png")
    plt.savefig(file_path)
    plt.close()
    return file_path

def generate_admin_chart(moodtracking_col):
    """Generate sentiment chart for all users combined."""
    logs = list(moodtracking_col.find())
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}

    for log in logs:
        mood = log.get("mood")
        category = mood_sentiment_map.get(mood, "neutral")
        sentiments[category] += 1

    labels = list(sentiments.keys())
    values = list(sentiments.values())

    plt.figure(figsize=(6, 4))
    plt.pie(values, labels=labels, autopct="%1.1f%%", colors=["green", "blue", "red"])
    plt.title("All Users' Sentiment Distribution")
    file_path = os.path.join(CHART_DIR, "admin_sentiment.png")
    plt.savefig(file_path)
    plt.close()
    return file_path
