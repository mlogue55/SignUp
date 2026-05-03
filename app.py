from flask import Flask, jsonify, request, render_template
import json
import os
import threading

app = Flask(__name__)
lock = threading.Lock()

DATA_FILE = os.environ.get("DATA_FILE", "data.json")

# Update these names for your group (First Initial + Last Name)
NAMES = [
    "J. Smith",
    "M. Johnson",
    "T. Williams",
    "K. Davis",
]


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"items": [], "next_id": 1}


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE) if os.path.dirname(DATA_FILE) else ".", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


@app.route("/")
def index():
    return render_template("index.html", names=NAMES)


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
        }
        data["items"].append(new_item)
        data["next_id"] += 1
        save_data(data)

    return jsonify(new_item), 201


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
