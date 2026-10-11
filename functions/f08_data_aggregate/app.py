import time
from flask import Flask, jsonify
import pandas as pd
import numpy as np

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def aggregate_data():
    t0 = time.time()
    n = 20000
    df = pd.DataFrame({
        "device_id": np.random.randint(1, 50, n),
        "metric_a": np.random.exponential(1.5, n),
        "metric_b": np.random.normal(10.0, 2.0, n),
        "region": np.random.choice(["us-east", "eu-central", "ap-south"], n)
    })
    grouped = df.groupby(["region", "device_id"]).agg({
        "metric_a": ["mean", "max"],
        "metric_b": ["mean", "std"]
    })
    elapsed_ms = (time.time() - t0) * 1000.0

    return jsonify({
        "function": "f08_data_aggregate",
        "rows_processed": n,
        "groups_formed": len(grouped),
        "compute_time_ms": elapsed_ms
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
