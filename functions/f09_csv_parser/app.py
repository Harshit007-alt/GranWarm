import io
import time
from flask import Flask, jsonify
import pandas as pd
import numpy as np

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def parse_csv():
    t0 = time.time()
    # Generate in-memory CSV
    csv_buf = io.StringIO()
    csv_buf.write("id,feature1,feature2,category\n")
    for i in range(5000):
        csv_buf.write(f"{i},{np.random.rand():.4f},{np.random.rand():.4f},cat_{i%10}\n")
    csv_buf.seek(0)

    df = pd.read_csv(csv_buf)
    summary = {
        "mean_f1": float(df["feature1"].mean()),
        "mean_f2": float(df["feature2"].mean()),
        "rows": len(df)
    }
    elapsed_ms = (time.time() - t0) * 1000.0

    return jsonify({
        "function": "f09_csv_parser",
        "summary": summary,
        "compute_time_ms": elapsed_ms
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
