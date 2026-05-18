from flask import Flask, jsonify, request, render_template, session, redirect, url_for
import json
import os
import secrets
import threading
from datetime import datetime, timezone

app = Flask(__name__)
lock = threading.Lock()

DATA_FILE    = os.environ.get("DATA_FILE",    "data.json")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "vacation")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

NAMES = [
    "M&M",
    "Justin",
    "D&D",
    "Clarks",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"items": [], "comments": [], "next_id": 1, "next_comment_id": 1}


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE) if os.path.dirname(DATA_FILE) else ".", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.before_request
def require_login():
    if request.endpoint in ("login", "logout", "static"):
        return
    if not session.get("authenticated"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if secrets.compare_digest(pwd, APP_PASSWORD):
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Incorrect password — try again."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Page ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", names=NAMES)


# ── Sign-up items ─────────────────────────────────────────────────────────────

@app.route("/api/items", methods=["GET"])
def get_items():
    with lock:
        data = load_data()
    return jsonify(data["items"])


@app.route("/api/items", methods=["POST"])
def add_item():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()

    if not name:
        return jsonify({"error": "Item name cannot be empty."}), 400
    if len(name) > 80:
        return jsonify({"error": "Item name is too long (max 80 characters)."}), 400

    with lock:
        data = load_data()
        if any(item["name"].lower() == name.lower() for item in data["items"]):
            return jsonify({"error": f'"{name}" is already on the list.'}), 409

        new_item = {
            "id": data["next_id"],
            "name": name,
            "signed_up_by": None,
            "checked": False,
        }
        data["items"].append(new_item)
        data["next_id"] += 1
        save_data(data)

    return jsonify(new_item), 201


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    with lock:
        data = load_data()
        before = len(data["items"])
        data["items"] = [i for i in data["items"] if i["id"] != item_id]
        if len(data["items"]) == before:
            return jsonify({"error": "Item not found."}), 404
        save_data(data)
    return jsonify({"ok": True})


@app.route("/api/items/<int:item_id>/check", methods=["POST"])
def toggle_item_check(item_id):
    with lock:
        data = load_data()
        for item in data["items"]:
            if item["id"] == item_id:
                item["checked"] = not item.get("checked", False)
                save_data(data)
                return jsonify(item)
    return jsonify({"error": "Item not found."}), 404


@app.route("/api/items/<int:item_id>/signup", methods=["POST"])
def signup(item_id):
    body = request.get_json(silent=True) or {}
    person = body.get("person", "").strip()

    if not person or person not in NAMES:
        return jsonify({"error": "Please select a valid name."}), 400

    with lock:
        data = load_data()
        for item in data["items"]:
            if item["id"] == item_id:
                if item["signed_up_by"]:
                    return jsonify({"error": f'Already claimed by {item["signed_up_by"]}.'}), 409
                item["signed_up_by"] = person
                save_data(data)
                return jsonify(item)

    return jsonify({"error": "Item not found."}), 404


@app.route("/api/items/<int:item_id>/signup", methods=["DELETE"])
def clear_signup(item_id):
    with lock:
        data = load_data()
        for item in data["items"]:
            if item["id"] == item_id:
                item["signed_up_by"] = None
                save_data(data)
                return jsonify(item)

    return jsonify({"error": "Item not found."}), 404


# ── Comments / thread ─────────────────────────────────────────────────────────

@app.route("/api/comments", methods=["GET"])
def get_comments():
    with lock:
        data = load_data()
    return jsonify(data.get("comments", []))


@app.route("/api/comments", methods=["POST"])
def post_comment():
    body = request.get_json(silent=True) or {}
    author = body.get("author", "").strip()
    text = body.get("text", "").strip()

    if not author or author not in NAMES:
        return jsonify({"error": "Please select your name first."}), 400
    if not text:
        return jsonify({"error": "Comment cannot be empty."}), 400
    if len(text) > 500:
        return jsonify({"error": "Too long (max 500 characters)."}), 400

    with lock:
        data = load_data()
        new_comment = {
            "id": data.get("next_comment_id", 1),
            "author": author,
            "text": text,
            "timestamp": now_iso(),
            "resolved": False,
            "replies": [],
            "next_reply_id": 1,
        }
        data.setdefault("comments", []).append(new_comment)
        data["next_comment_id"] = data.get("next_comment_id", 1) + 1
        save_data(data)

    return jsonify(new_comment), 201


@app.route("/api/comments/<int:comment_id>/replies", methods=["POST"])
def post_reply(comment_id):
    body = request.get_json(silent=True) or {}
    author = body.get("author", "").strip()
    text = body.get("text", "").strip()

    if not author or author not in NAMES:
        return jsonify({"error": "Please select your name first."}), 400
    if not text:
        return jsonify({"error": "Reply cannot be empty."}), 400
    if len(text) > 500:
        return jsonify({"error": "Too long (max 500 characters)."}), 400

    with lock:
        data = load_data()
        for comment in data.get("comments", []):
            if comment["id"] == comment_id:
                reply = {
                    "id": comment.get("next_reply_id", 1),
                    "author": author,
                    "text": text,
                    "timestamp": now_iso(),
                }
                comment["replies"].append(reply)
                comment["next_reply_id"] = comment.get("next_reply_id", 1) + 1
                save_data(data)
                return jsonify(reply), 201

    return jsonify({"error": "Comment not found."}), 404


@app.route("/api/comments/<int:comment_id>/resolve", methods=["POST"])
def resolve_comment(comment_id):
    with lock:
        data = load_data()
        for comment in data.get("comments", []):
            if comment["id"] == comment_id:
                comment["resolved"] = not comment.get("resolved", False)
                save_data(data)
                return jsonify(comment)

    return jsonify({"error": "Comment not found."}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
