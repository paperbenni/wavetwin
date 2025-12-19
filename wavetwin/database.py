import sqlite3


def init_db(db_file):
    """Initialize SQLite database for storing fingerprints."""
    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    # Enable Write-Ahead Logging for concurrency/stability
    c.execute("PRAGMA journal_mode=WAL;")

    # Table to store file info
    c.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE,
            filename TEXT,
            size INTEGER,
            mtime REAL,
            duration INTEGER,
            fingerprint TEXT,
            bitrate INTEGER,
            sample_rate INTEGER,
            codec TEXT,
            processed INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    return conn


def get_unprocessed_files(conn):
    """Get all files that haven't been processed yet."""
    c = conn.cursor()
    c.execute("SELECT id, path, size, mtime FROM tracks WHERE processed = 0")
    return c.fetchall()


def update_track_processing(conn, track_id, fingerprint, metadata):
    """Update track with fingerprint and metadata."""
    c = conn.cursor()
    c.execute(
        """
        UPDATE tracks 
        SET fingerprint = ?, filename = ?, duration = ?, 
            bitrate = ?, sample_rate = ?, codec = ?, processed = 1
        WHERE id = ?
    """,
        (
            fingerprint,
            metadata["filename"],
            metadata["duration"],
            metadata["bitrate"],
            metadata["sample_rate"],
            metadata["codec"],
            track_id,
        ),
    )
    conn.commit()


def add_file_if_needed(conn, filepath, size, mtime):
    """Add file to database if it doesn't exist or needs updating."""
    c = conn.cursor()
    c.execute("SELECT id, size, mtime FROM tracks WHERE path = ?", (filepath,))
    result = c.fetchone()

    if result:
        db_id, db_size, db_mtime = result
        if size == db_size and mtime == db_mtime:
            return None  # File unchanged, skip processing

        # File changed, update it
        c.execute(
            "UPDATE tracks SET size = ?, mtime = ?, processed = 0 WHERE id = ?",
            (size, mtime, db_id),
        )
        conn.commit()
        return db_id
    else:
        # New file, add it
        c.execute(
            "INSERT INTO tracks (path, size, mtime, processed) VALUES (?, ?, ?, 0)",
            (filepath, size, mtime),
        )
        conn.commit()
        return c.lastrowid


def get_all_fingerprints(conn):
    """Get all processed fingerprints for duplicate detection."""
    c = conn.cursor()
    c.execute(
        "SELECT path, filename, size, duration, fingerprint FROM tracks WHERE processed = 1"
    )
    return c.fetchall()


def get_duplicate_groups(conn):
    """Get groups of files with identical fingerprints."""
    c = conn.cursor()
    c.execute("""
        SELECT path, filename, size, duration, fingerprint, bitrate, sample_rate
        FROM tracks 
        WHERE processed = 1 AND fingerprint IN (
            SELECT fingerprint 
            FROM tracks 
            WHERE processed = 1 
            GROUP BY fingerprint 
            HAVING COUNT(*) > 1
        )
        ORDER BY fingerprint
    """)
    return c.fetchall()
