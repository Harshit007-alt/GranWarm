import io
import time
from flask import Flask, jsonify, request
from PIL import Image
import numpy as np

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def resize_image():
    t0 = time.time()
    # Create synthetic 1024x1024 RGB image
    arr = np.random.randint(0, 256, (1024, 1024, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    # Resize to 256x256
    resized = img.resize((256, 256), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG")
    elapsed_ms = (time.time() - t0) * 1000.0

    return jsonify({
        "function": "f03_image_resize",
        "original_size": [1024, 1024],
        "resized_size": [256, 256],
        "bytes": len(buf.getvalue()),
        "compute_time_ms": elapsed_ms
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
