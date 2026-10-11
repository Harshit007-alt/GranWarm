import sqlite3
import time
import uuid
from flask import Flask, jsonify

app = Flask(__name__)

# Setup in-memory SQLite order table
_conn = sqlite3.connect(":memory:", check_same_thread=False)
with _conn:
    _conn.execute("CREATE TABLE orders (id TEXT PRIMARY KEY, amount REAL, status TEXT, created_at REAL)")

@app.route("/", methods=["GET", "POST"])
def process_order():
    t0 = time.time()
    order_id = str(uuid.uuid4())
    amount = 49.99
    with _conn:
        _conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?)",
            (order_id, amount, "COMPLETED", t0)
        )
    elapsed_ms = (time.time() - t0) * 1000.0

    return jsonify({
        "function": "f11_order_process",
        "order_id": order_id,
        "amount": amount,
        "status": "COMPLETED",
        "compute_time_ms": elapsed_ms
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
