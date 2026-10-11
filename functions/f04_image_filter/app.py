import time
from flask import Flask, jsonify
from PIL import Image, ImageFilter
import numpy as np

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def filter_image():
    t0 = time.time()
    arr = np.random.randint(0, 256, (512, 512, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    # Apply Gaussian blur & edge enhance filters
    blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
    edges = blurred.filter(ImageFilter.EDGE_ENHANCE_MORE)
    elapsed_ms = (time.time() - t0) * 1000.0

    return jsonify({
        "function": "f04_image_filter",
        "filter_applied": ["GaussianBlur", "EdgeEnhance"],
        "size": list(edges.size),
        "compute_time_ms": elapsed_ms
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
