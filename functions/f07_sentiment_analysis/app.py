import time
from flask import Flask, jsonify, request
import numpy as np

app = Flask(__name__)

# Mock sentiment lexicon and weights
_VOCAB = {"great": 1.0, "excellent": 1.5, "poor": -1.2, "terrible": -1.8, "fast": 0.8, "bug": -1.0}

@app.route("/", methods=["GET", "POST"])
def analyze_sentiment():
    t0 = time.time()
    text = "GranuWarm provides excellent adaptive performance and eliminates serverless cold start delay"
    tokens = text.lower().split()
    score = sum(_VOCAB.get(w, 0.0) for w in tokens)
    # Heavy tensor operations to emulate transformer layer matrix multiplies
    m = np.random.randn(256, 256)
    for _ in range(5):
        m = m @ m / 256.0

    elapsed_ms = (time.time() - t0) * 1000.0

    return jsonify({
        "function": "f07_sentiment_analysis",
        "tokens": len(tokens),
        "sentiment_score": float(score),
        "norm": float(np.linalg.norm(m)),
        "compute_time_ms": elapsed_ms
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
