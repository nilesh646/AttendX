import os
from insightface.app import FaceAnalysis

MODEL_ROOT = os.environ.get(
    "INSIGHTFACE_MODEL_ROOT",
    "/var/data/models"
)

os.makedirs(MODEL_ROOT, exist_ok=True)

print("Downloading InsightFace model (first deployment only)...")

app = FaceAnalysis(
    name="buffalo_l",
    root=MODEL_ROOT,
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=-1,
    det_size=(640,640)
)

print("InsightFace ready.")