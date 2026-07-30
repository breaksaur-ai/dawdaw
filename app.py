# --- app.py ---
import asyncio
import os
import json
from functools import wraps
from flask import (
    Flask, render_template, request,
    jsonify, session, redirect, url_for
)
from dotenv import load_dotenv
from reporter import report_condo_games_with_proxy

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["authed"] = True
            return redirect(url_for("index"))
        error = "Invalid password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/api/report", methods=["POST"])
@login_required
def api_report():
    data = request.get_json()
    cookie = (data.get("cookie") or "").strip()
    raw_places = (data.get("place_ids") or "").strip()
    raw_proxies = (data.get("proxies") or "").strip()

    if not cookie:
        return jsonify({"error": "Cookie is required."}), 400
    if not raw_places:
        return jsonify({"error": "At least one place ID is required."}), 400

    place_ids = []
    for line in raw_places.splitlines():
        line = line.strip()
        if line.isdigit():
            place_ids.append(int(line))

    if not place_ids:
        return jsonify({"error": "No valid place IDs found."}), 400

    proxies = []
    for line in raw_proxies.splitlines():
        line = line.strip()
        if line:
            if not line.startswith("http"):
                line = f"http://{line}"
            proxies.append(line)

    try:
        results = asyncio.run(
            report_condo_games_with_proxy(cookie, place_ids, proxies)
        )
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
