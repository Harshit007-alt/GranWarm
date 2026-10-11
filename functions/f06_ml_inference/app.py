import time
from flask import Flask, jsonify
import numpy as np
from sklearn.linear_model import Ridge

app = Flask(__name__)

# Pre-train a lightweight model at module load (simulating cold init)
_X_train = np.random.randn(200, 20)
_y_train = _X_train @ np.ones(20) + np.random.randn(200) * 0.1
_model = Ridge().fit(_X_train, _y_train)

@app.route("/", methods=["GET", "POST"])
def predict():
    t0 = time.time()
    X_test = np.random.randn(50, 20)
    preds = _model.predict(X_test)
    elapsed_ms = (time.time() - t0) * 1000.0

    return jsonify({
        "function": "f06_ml_inference",
        "samples_evaluated": len(preds),
        "mean_prediction": float(np.mean(preds)),
        "compute_time_ms": elapsed_ms
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
