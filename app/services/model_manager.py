import os
import logging
from insightface.app import FaceAnalysis

logger = logging.getLogger(__name__)

def ensure_insightface_models():
    """
    Downloads buffalo_l automatically if missing.
    """

    model_root = os.environ.get(
        "INSIGHTFACE_MODEL_ROOT",
        "/var/data/models"
    )

    os.makedirs(model_root, exist_ok=True)

    logger.info("Checking InsightFace models...")

    app = FaceAnalysis(
        name="buffalo_l",
        root=model_root,
        providers=["CPUExecutionProvider"]
    )

    app.prepare(
        ctx_id=-1,
        det_size=(640,640)
    )

    logger.info("InsightFace models ready.")