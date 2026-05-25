import os
import sqlite3
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Flask, g, redirect, render_template, request, url_for, flash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
DB_PATH = DATA_DIR / "volleyball.db"
DEFAULT_STATS = ["Dig", "Kill", "Assist", "Ace", "Service Error", "Block"]
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            number TEXT,
            position TEXT,
            photo TEXT,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS stat_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opponent TEXT,
            location TEXT,
            notes TEXT,
            started_at TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            set_number INTEGER NOT NULL,
            our_score INTEGER,
            their_score INTEGER,
            completed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(match_id) REFERENCES matches(id)
        );
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            set_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(match_id) REFERENCES matches(id),
            FOREIGN KEY(set_id) REFERENCES sets(id),
            FOREIGN KEY(player_id) REFERENCES players(id),
            FOREIGN KEY(category_id) REFERENCES stat_categories(id)
        );
        """
    )
    for stat in DEFAULT_STATS:
        conn.execute("INSERT OR IGNORE INTO stat_categories(name) VALUES (?)", (stat,))
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def current_set(match_id):
    return db().execute(
        "SELECT * FROM sets WHERE match_id=? AND completed=0 ORDER BY set_number DESC LIMIT 1",
        (match_id,),
    ).fetchone()


def get_match(match_id):
    return db().execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()


@app.route("/")
def index():
    matches = db().execute(
        "SELECT m.*, COUNT(s.id) AS total_stats FROM matches m LEFT JOIN stats s ON s.match_id=m.id GROUP BY m.id ORDER BY m.started_at DESC"
    ).fetchall()
    return render_template("index.html", matches=matches)


@app.route("/settings")
def settings():
    players = db().execute("SELECT * FROM players WHERE active=1 ORDER BY CAST(number AS INTEGER), name").fetchall()
    categories = db().execute("SELECT * FROM stat_categories WHERE active=1 ORDER BY name").fetchall()
    return render_template("settings.html", players=players, categories=categories)


@app.post("/settings/players")
def add_player():
    name = request.form.get("name", "").strip()
    number = request.form.get("number", "").strip()
    position = request.form.get("position", "").strip()
    photo_name = None
    file = request.files.get("photo")
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        photo_name = f"{stamp}_{filename}"
        file.save(UPLOAD_DIR / photo_name)
    if name:
        db().execute(
            "INSERT INTO players(name, number, position, photo) VALUES (?, ?, ?, ?)",
            (name, number, position, photo_name),
        )
        db().commit()
        flash("Player added.")
    return redirect(url_for("settings"))


@app.post("/settings/players/<int:player_id>/delete")
def delete_player(player_id):
    db().execute("UPDATE players SET active=0 WHERE id=?", (player_id,))
    db().commit()
    flash("Player removed from active roster.")
    return redirect(url_for("settings"))


@app.post("/settings/categories")
def add_category():
    name = request.form.get("name", "").strip().title()
    if name:
        db().execute("INSERT OR IGNORE INTO stat_categories(name) VALUES (?)", (name,))
        db().commit()
        flash("Stat category added.")
    return redirect(url_for("settings"))


@app.post("/settings/categories/<int:category_id>/delete")
def delete_category(category_id):
    db().execute("UPDATE stat_categories SET active=0 WHERE id=?", (category_id,))
    db().commit()
    flash("Stat category hidden.")
    return redirect(url_for("settings"))


@app.post("/matches")
def create_match():
    opponent = request.form.get("opponent", "").strip()
    location = request.form.get("location", "").strip()
    notes = request.form.get("notes", "").strip()
    cur = db().execute(
        "INSERT INTO matches(opponent, location, notes, started_at) VALUES (?, ?, ?, ?)",
        (opponent, location, notes, datetime.now().isoformat(timespec="seconds")),
    )
    match_id = cur.lastrowid
    db().execute("INSERT INTO sets(match_id, set_number) VALUES (?, 1)", (match_id,))
    db().commit()
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>")
def match_detail(match_id):
    match = get_match(match_id)
    if not match:
        return redirect(url_for("index"))
    active_set = current_set(match_id)
    if not active_set:
        last = db().execute("SELECT MAX(set_number) AS n FROM sets WHERE match_id=?", (match_id,)).fetchone()["n"] or 0
        db().execute("INSERT INTO sets(match_id, set_number) VALUES (?, ?)", (match_id, last + 1))
        db().commit()
        active_set = current_set(match_id)
    players = db().execute("SELECT * FROM players WHERE active=1 ORDER BY CAST(number AS INTEGER), name").fetchall()
    categories = db().execute("SELECT * FROM stat_categories WHERE active=1 ORDER BY name").fetchall()
    totals = db().execute(
        """
        SELECT p.id AS player_id, c.name AS category, COUNT(s.id) AS total
        FROM players p CROSS JOIN stat_categories c
        LEFT JOIN stats s ON s.player_id=p.id AND s.category_id=c.id AND s.match_id=?
        WHERE p.active=1 AND c.active=1
        GROUP BY p.id, c.id
        """,
        (match_id,),
    ).fetchall()
    stat_map = {}
    for row in totals:
        stat_map.setdefault(row["player_id"], {})[row["category"]] = row["total"]
    sets = db().execute("SELECT * FROM sets WHERE match_id=? ORDER BY set_number", (match_id,)).fetchall()
    return render_template("match.html", match=match, active_set=active_set, players=players, categories=categories, stat_map=stat_map, sets=sets)


@app.post("/matches/<int:match_id>/stats")
def add_stat(match_id):
    set_id = request.form.get("set_id")
    player_id = request.form.get("player_id")
    category_id = request.form.get("category_id")
    if set_id and player_id and category_id:
        db().execute(
            "INSERT INTO stats(match_id, set_id, player_id, category_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (match_id, set_id, player_id, category_id, datetime.now().isoformat(timespec="seconds")),
        )
        db().commit()
        flash("Stat recorded.")
    return redirect(url_for("match_detail", match_id=match_id))


@app.post("/matches/<int:match_id>/next-set")
def next_set(match_id):
    set_id = request.form.get("set_id")
    our_score = request.form.get("our_score") or None
    their_score = request.form.get("their_score") or None
    db().execute(
        "UPDATE sets SET our_score=?, their_score=?, completed=1 WHERE id=?",
        (our_score, their_score, set_id),
    )
    last = db().execute("SELECT MAX(set_number) AS n FROM sets WHERE match_id=?", (match_id,)).fetchone()["n"] or 0
    db().execute("INSERT INTO sets(match_id, set_number) VALUES (?, ?)", (match_id, last + 1))
    db().commit()
    flash("Moved to next set.")
    return redirect(url_for("match_detail", match_id=match_id))


@app.post("/matches/<int:match_id>/complete")
def complete_match(match_id):
    db().execute("UPDATE matches SET completed=1 WHERE id=?", (match_id,))
    db().commit()
    flash("Match marked complete.")
    return redirect(url_for("index"))


@app.route("/matches/<int:match_id>/summary")
def summary(match_id):
    match = get_match(match_id)
    rows = db().execute(
        """
        SELECT p.number, p.name, p.position, c.name AS category, COUNT(s.id) AS total
        FROM stats s
        JOIN players p ON p.id=s.player_id
        JOIN stat_categories c ON c.id=s.category_id
        WHERE s.match_id=?
        GROUP BY p.id, c.id
        ORDER BY CAST(p.number AS INTEGER), p.name, c.name
        """,
        (match_id,),
    ).fetchall()
    sets = db().execute("SELECT * FROM sets WHERE match_id=? ORDER BY set_number", (match_id,)).fetchall()
    return render_template("summary.html", match=match, rows=rows, sets=sets)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
