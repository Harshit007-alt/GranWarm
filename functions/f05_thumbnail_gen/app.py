import io
import time
from flask import Flask, jsonify
from PIL import Image
import numpy as np

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def generate_thumbnail():
    t0 = time.time()
    arr = np.random.randint(0, 256, (640, 480, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    img.thumbnail((128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    elapsed_ms = (time.time() - t0) * 1000.0

    return jsonify({
        "function": "f05_thumbnail_gen",
        "thumbnail_size": list(img.size),
        "bytes": len(buf.getvalue()),
        "compute_time_ms": elapsed_ms
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
