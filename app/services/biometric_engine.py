import os
import cv2
import base64
import logging
import numpy as np
from flask import current_app

logger = logging.getLogger(__name__)


class BiometricEngine:
    """Singleton biometric engine that loads models once."""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None

    def __init__(self):
        self._backend = "none"
        self._face_app = None
        self._spoof_models = []
        self._spoof_detector = None
        self._image_cropper = None
        self._init_backend()

    def _init_backend(self):
        """Try to load InsightFace + Silent-Face, fall back to DeepFace."""
        try:
            self._init_insightface()
            self._init_silent_face()
            self._backend = "full"
            logger.info("BiometricEngine: Full backend (InsightFace + Silent-Face) loaded.")
        except Exception as e:
            logger.warning(f"BiometricEngine: Full backend failed ({e}), trying DeepFace...")
            try:
                self._init_deepface()
                self._backend = "deepface"
                logger.info("BiometricEngine: DeepFace fallback loaded.")
            except Exception as e2:
                logger.error(f"BiometricEngine: No backend available ({e2}). Face match disabled.")
                self._backend = "none"

    def _init_insightface(self):

        from insightface.app import FaceAnalysis

        model_root = os.environ.get(
            "INSIGHTFACE_MODEL_ROOT",
            os.path.join(os.getcwd(), "models")
        )

        model_name = os.environ.get(
            "INSIGHTFACE_MODEL_NAME",
            "buffalo_l"
        )

        os.makedirs(model_root, exist_ok=True)

        logger.info(f"Loading InsightFace model from {model_root}")

        self._face_app = FaceAnalysis(
            name=model_name,
            root=model_root,
            providers=["CPUExecutionProvider"]
        )

        self._face_app.prepare(
            ctx_id=-1,
            det_size=(640,640)
        )

        logger.info("InsightFace loaded successfully.")

    def _init_silent_face(self):
        import sys
        src_path = os.path.join(os.getcwd(), "src")
        if os.path.exists(src_path) and src_path not in sys.path:
            sys.path.insert(0, src_path)

        from anti_spoof_predict import AntiSpoofPredict, Detection
        from generate_patches import CropImage
        from utility import parse_model_name

        model_dir = os.environ.get("LIVENESS_MODEL_DIR",
                                    os.path.join(current_app.root_path,"static", "resources", "anti_spoof_models"))

        if not os.path.isdir(model_dir):
            raise FileNotFoundError(f"Liveness model dir not found: {model_dir}")

        self._spoof_detector = AntiSpoofPredict(0)
        self._image_cropper = CropImage()

        for model_name in os.listdir(model_dir):
            if not model_name.endswith('.pth'):
                continue
            h_input, w_input, model_type, scale = parse_model_name(model_name)
            self._spoof_models.append({
                'path': os.path.join(model_dir, model_name),
                'h': h_input, 'w': w_input,
                'scale': scale, 'model_type': model_type,
            })

        if not self._spoof_models:
            raise FileNotFoundError("No .pth liveness models found.")

    def _init_deepface(self):
        from deepface import DeepFace
        # Trigger model download/load
        DeepFace.build_model("ArcFace")

    # ═══════════════════════════════════════════
    #  PUBLIC API
    # ═══════════════════════════════════════════

    def check_liveness(self, image: np.ndarray) -> dict:
        """
        Check if the image contains a real, single human face.
        Returns: {is_real: bool, bbox: list|None, reason: str}
        """
        if self._backend == "full":
            return self._liveness_silent_face(image)
        elif self._backend == "deepface":
            return self._liveness_deepface(image)
        return {"is_real": True, "bbox": None, "reason": "No liveness backend available."}

    def get_embedding(self, image: np.ndarray) -> np.ndarray | None:
        """Extract 512-d face embedding. Returns None if no single face found."""
        if self._backend == "full":
            return self._embedding_insightface(image)
        elif self._backend == "deepface":
            return self._embedding_deepface(image)
        return None

    def compare_embeddings(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Cosine similarity between two normalized embeddings."""
        return float(np.dot(emb1, emb2))

    def compare_with_centroid(self, history_path: str, live_emb: np.ndarray) -> float:
        """Compare live embedding against centroid of historical embeddings."""
        if not os.path.exists(history_path):
            return 0.0
        history = np.load(history_path)
        if len(history.shape) == 1:
            history = history.reshape(1, -1)
        centroid = np.mean(history, axis=0)
        centroid = centroid / (np.linalg.norm(centroid) + 1e-8)
        return float(np.dot(centroid, live_emb))

    def update_embedding_history(self, history_path: str, new_emb: np.ndarray, max_entries: int = 50):
        """Append new embedding to history for centroid self-improvement."""
        if os.path.exists(history_path):
            history = np.load(history_path)
            if len(history.shape) == 1:
                history = history.reshape(1, -1)
            history = np.vstack([history, new_emb.reshape(1, -1)])
            if len(history) > max_entries:
                history = history[-max_entries:]
        else:
            os.makedirs(os.path.dirname(history_path), exist_ok=True)
            history = new_emb.reshape(1, -1)
        np.save(history_path, history)

    # ═══════════════════════════════════════════
    #  SILENT-FACE BACKEND
    # ═══════════════════════════════════════════

    def _liveness_silent_face(self, image: np.ndarray) -> dict:
        from utility import parse_model_name

        bbox = self._spoof_detector.get_bbox(image)

        if bbox == "MULTIPLE_FACES":
            return {"is_real": False, "bbox": None,
                    "reason": "Multiple faces detected. Only one person allowed."}
        if bbox is None:
            return {"is_real": False, "bbox": None,
                    "reason": "No face detected. Ensure your face is clearly visible."}

        prediction = np.zeros((1, 3))
        for model_info in self._spoof_models:
            param = {
                "org_img": image, "bbox": bbox,
                "scale": model_info['scale'],
                "out_w": model_info['w'], "out_h": model_info['h'],
                "crop": model_info['scale'] is not None,
            }
            img_patch = self._image_cropper.crop(**param)
            prediction += self._spoof_detector.predict(img_patch, model_info['path'])

        label = np.argmax(prediction)
        is_real = (label == 1)

        if not is_real:
            return {"is_real": False, "bbox": bbox,
                    "reason": "Spoof detected. Please use a real live photo."}
        return {"is_real": True, "bbox": bbox, "reason": "Liveness verified."}

    def _embedding_insightface(self, image: np.ndarray) -> np.ndarray | None:
        faces = self._face_app.get(image)
        if len(faces) == 0:
            return None
            
        # 🔥 FIX: Sort faces by bounding box size (width * height) and pick the biggest one
        # This prevents the app from crashing if another student is in the background
        faces = sorted(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]), reverse=True)
        
        return faces[0].normed_embedding

    # ═══════════════════════════════════════════
    #  DEEPFACE FALLBACK
    # ═══════════════════════════════════════════

    def _liveness_deepface(self, image: np.ndarray) -> dict:
        from deepface import DeepFace
        try:
            faces = DeepFace.extract_faces(
                img_path=image, detector_backend="opencv",
                enforce_detection=True, anti_spoofing=True
            )
            if not faces:
                return {"is_real": False, "bbox": None, "reason": "No face detected."}
            face = faces[0]
            is_real = face.get("is_real", True)
            score = face.get("antispoof_score", 1.0)
            if not is_real or score < 0.60:
                return {"is_real": False, "bbox": None,
                        "reason": "Spoof detected. Please take a real photo."}
            return {"is_real": True, "bbox": None, "reason": "Liveness verified."}
        except ValueError:
            return {"is_real": False, "bbox": None, "reason": "No face detected."}
        except Exception as e:
            return {"is_real": False, "bbox": None, "reason": f"Error: {str(e)}"}

    def _embedding_deepface(self,image):

        from deepface import DeepFace

        try:

            results=DeepFace.represent(
                img_path=image,
                model_name="ArcFace",
                detector_backend="opencv",
                enforce_detection=True
            )

            if results:

                results=sorted(
                    results,
                    key=lambda r:
                    r["facial_area"]["w"]*
                    r["facial_area"]["h"],
                    reverse=True
                )

                emb=np.array(
                    results[0]["embedding"],
                    dtype=np.float32
                )

                emb=emb/np.linalg.norm(emb)

                return emb

        except Exception as e:

            logger.error(e)

        return None


# ═══════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def decode_base64_image(base64_str: str) -> np.ndarray:
    """Decode a base64 image string to OpenCV numpy array."""
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    img_bytes = base64.b64decode(base64_str)
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image.")
    return img


def save_image_from_base64(base64_str: str, filepath: str) -> str:
    """Save base64 image to disk and return the filepath."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(base64_str))
    return filepath


def get_safe_username(email: str, name: str) -> str:
    """Generate a filesystem-safe username from email + name."""
    raw = email.split("@")[0] + "_" + name.replace(" ", "_").lower()
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in raw)


def get_master_photo_path(username: str) -> str:
    from flask import current_app
    user_dir = os.path.join(current_app.config["MASTER_PHOTO_FOLDER"], username)
    return os.path.join(user_dir, "master.jpg")


def get_embedding_path(username: str) -> str:
    from flask import current_app
    user_dir = os.path.join(current_app.config["EMBEDDING_FOLDER"], username)
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, "master.npy")


def get_embedding_history_path(username: str) -> str:
    from flask import current_app
    user_dir = os.path.join(current_app.config["EMBEDDING_FOLDER"], username)
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, "history.npy")


def get_selfie_path(username: str, date_str: str, session_id) -> str:
    from flask import current_app
    user_dir = os.path.join(current_app.config["SELFIE_FOLDER"], username)
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, f"selfie_{date_str}_{session_id}.jpg")
