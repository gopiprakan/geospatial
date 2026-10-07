"""Storage repository service using SQLite for file metadata and measurements persistence."""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.exceptions import RecordNotFoundError


class StorageService:
    """Thread-safe SQLite storage for geospatial file metadata and calculated measurements."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.database_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create or return an SQLite connection."""
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema tables."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_records (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        feature_count INTEGER NOT NULL,
                        crs TEXT NOT NULL,
                        status TEXT NOT NULL,
                        measurements TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.commit()

    def save_file_record(
        self,
        file_id: str,
        filename: str,
        feature_count: int,
        crs: str,
        status: str,
        measurements: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Save a new file record and associated measurements."""
        measurements_json = json.dumps(measurements, default=str)
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO file_records (id, filename, feature_count, crs, status, measurements)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        filename=excluded.filename,
                        feature_count=excluded.feature_count,
                        crs=excluded.crs,
                        status=excluded.status,
                        measurements=excluded.measurements;
                    """,
                    (file_id, filename, feature_count, crs, status, measurements_json),
                )
                conn.commit()

        return {
            "id": file_id,
            "filename": filename,
            "feature_count": feature_count,
            "crs": crs,
            "status": status,
        }

    def get_file_record(self, file_id: str) -> Dict[str, Any]:
        """
        Retrieve file metadata by ID.

        Raises:
            RecordNotFoundError: If record is not found.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, filename, feature_count, crs, status FROM file_records WHERE id = ?",
                    (file_id,),
                )
                row = cursor.fetchone()

        if not row:
            raise RecordNotFoundError(file_id)

        return {
            "id": row["id"],
            "filename": row["filename"],
            "feature_count": row["feature_count"],
            "crs": row["crs"],
            "status": row["status"],
        }

    def get_measurements(self, file_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve measurements by file ID.

        Raises:
            RecordNotFoundError: If record is not found.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT measurements FROM file_records WHERE id = ?",
                    (file_id,),
                )
                row = cursor.fetchone()

        if not row:
            raise RecordNotFoundError(file_id)

        return json.loads(row["measurements"])

    def clear(self) -> None:
        """Clear all records (primarily for testing)."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM file_records;")
                conn.commit()


storage_service = StorageService()
