"""Private file storage and upload validation for progress evidence.

Files are written under PRIVATE_UPLOAD_DIR with random names and are never
served by a static route; they are only returned by the authorized download
endpoint. Validation: size limit, an allow-list of image signatures, and a
full decode with Pillow (which also enforces its decompression-bomb limit).
"""

import base64
import hashlib
import hmac
import io
import time
import uuid
from pathlib import Path

from PIL import Image

from app.core.config import settings

ALLOWED = {
    "jpeg": ("image/jpeg", ".jpg"),
    "png": ("image/png", ".png"),
    "webp": ("image/webp", ".webp"),
}


class UploadRejected(Exception):
    pass


def sniff(content: bytes) -> str | None:
    """Identify the file type from its signature (not its name or header)."""
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image(content: bytes) -> tuple[str, str, str, tuple[int, int]]:
    if not content:
        raise UploadRejected("The file is empty.")
    if len(content) > settings.evidence_max_bytes:
        raise UploadRejected(f"The file is larger than {settings.evidence_max_bytes // (1024 * 1024)} MB.")
    kind = sniff(content)
    if kind is None:
        raise UploadRejected("Only JPEG, PNG or WebP photographs are accepted.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            size = image.size
            if (image.format or "").lower() not in {"jpeg", "png", "webp"}:
                raise UploadRejected("The image content does not match an accepted format.")
    except UploadRejected:
        raise
    except Exception as error:  # truncated, corrupt or oversized images
        raise UploadRejected("The image could not be read.") from error
    content_type, extension = ALLOWED[kind]
    return kind, content_type, extension, size


def scan_for_malware(path: Path) -> str:
    """Hook for an antivirus scanner. None is configured, so files are marked
    'not_scanned'; images are still fully decoded before acceptance."""
    return "not_scanned"


def storage_root() -> Path:
    root = Path(settings.private_upload_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[3] / root
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    return root


def save(content: bytes, extension: str) -> tuple[str, str]:
    key = f"evidence/{uuid.uuid4().hex}{extension}"
    path = storage_root() / key
    path.write_bytes(content)
    return key, hashlib.sha256(content).hexdigest()


def resolve(key: str) -> Path:
    root = storage_root().resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise UploadRejected("Invalid storage key")
    return path


def sign_link(evidence_id: str, user_id: str, seconds: int | None = None) -> tuple[str, int]:
    expires = int(time.time()) + (seconds or settings.download_link_seconds)
    message = f"{evidence_id}:{user_id}:{expires}".encode()
    signature = base64.urlsafe_b64encode(hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).digest()).decode().rstrip("=")
    return signature, expires


def verify_link(evidence_id: str, user_id: str, expires: int, signature: str) -> bool:
    if expires < int(time.time()):
        return False
    message = f"{evidence_id}:{user_id}:{expires}".encode()
    expected = base64.urlsafe_b64encode(hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).digest()).decode().rstrip("=")
    return hmac.compare_digest(expected, signature or "")
