# services/file_storage.py
# Saves uploaded photos and documents to disk under uploads/{ticket_id}/
# In production this would be the OEM document management system API.

import os, uuid, base64
from pathlib import Path
from datetime import datetime, timezone

UPLOADS_DIR    = 'uploads'
ALLOWED_IMAGES = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_DOCS   = {'.pdf'}
ALL_ALLOWED    = ALLOWED_IMAGES | ALLOWED_DOCS
MAX_FILE_SIZE  = 10 * 1024 * 1024  # 10MB


class FileStorageService:

    def __init__(self):
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        print(f"[FileStorage] Ready — uploads dir: {os.path.abspath(UPLOADS_DIR)}")

    def save_file(self, ticket_id: str, file_bytes: bytes,
                  original_filename: str, context: str = 'chat') -> dict:
        """
        Save an uploaded file.
        context: 'chat' (uploaded during conversation) or 'resolution' (at close)
        """
        ext = Path(original_filename).suffix.lower()

        if ext not in ALL_ALLOWED:
            return {'success': False,
                    'error': f"File type '{ext}' not allowed. Allowed: {sorted(ALL_ALLOWED)}"}

        if len(file_bytes) > MAX_FILE_SIZE:
            return {'success': False, 'error': 'File too large. Max 10MB.'}

        file_type = 'image' if ext in ALLOWED_IMAGES else 'document'

        ticket_dir = os.path.join(UPLOADS_DIR, ticket_id)
        os.makedirs(ticket_dir, exist_ok=True)

        file_id  = uuid.uuid4().hex[:12].upper()
        filename = f"{file_id}_{context}{ext}"
        filepath = os.path.join(ticket_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(file_bytes)

        print(f"[FileStorage] Saved {file_type}: {filename} ({len(file_bytes):,} bytes)")

        return {
            'success':           True,
            'file_id':           file_id,
            'filename':          filename,
            'filepath':          filepath,
            'url':               f"/uploads/{ticket_id}/{filename}",
            'file_type':         file_type,
            'context':           context,
            'original_filename': original_filename,
            'size_bytes':        len(file_bytes),
            'uploaded_at':       datetime.now(timezone.utc).isoformat(),
        }

    def get_file_path(self, ticket_id: str, filename: str) -> str:
        return os.path.join(UPLOADS_DIR, ticket_id, filename)

    def get_file_as_base64(self, ticket_id: str, filename: str) -> str:
        path = self.get_file_path(ticket_id, filename)
        if not os.path.exists(path):
            return None
        with open(path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def get_image_paths_for_llm(self, ticket_id: str, file_ids: list = None) -> list:
        """Return disk paths for images to pass directly to mistral."""
        ticket_dir = os.path.join(UPLOADS_DIR, ticket_id)
        if not os.path.exists(ticket_dir):
            return []
        paths = []
        for filename in os.listdir(ticket_dir):
            ext = Path(filename).suffix.lower()
            if ext not in ALLOWED_IMAGES:
                continue
            if file_ids:
                # Only include files matching the provided IDs
                if not any(filename.startswith(fid) for fid in file_ids):
                    continue
            paths.append(os.path.join(ticket_dir, filename))
        return paths

    def list_files(self, ticket_id: str) -> list:
        ticket_dir = os.path.join(UPLOADS_DIR, ticket_id)
        if not os.path.exists(ticket_dir):
            return []
        files = []
        for filename in os.listdir(ticket_dir):
            ext = Path(filename).suffix.lower()
            files.append({
                'filename':  filename,
                'url':       f"/uploads/{ticket_id}/{filename}",
                'file_type': 'image' if ext in ALLOWED_IMAGES else 'document',
                'size_bytes': os.path.getsize(os.path.join(ticket_dir, filename)),
            })
        return files


file_storage = FileStorageService()
