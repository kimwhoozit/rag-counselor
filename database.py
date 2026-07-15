import sqlite3
import json
import numpy as np
from typing import List, Dict, Any

DB_PATH = "knowledge_base.db"

def init_db():
    """Initializes the database by creating tables if they do not exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Category can be: 'document' (from files) or 'qa_history' (approved AI answers)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        category TEXT NOT NULL,
        embedding TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Store session-based chat logs (for memory representation in UI)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # File index tracking for automatic synchronization
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS indexed_files (
        filename TEXT PRIMARY KEY,
        last_modified REAL,
        indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # User authentication table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()

def get_indexed_files() -> Dict[str, float]:
    """Returns a dictionary mapping filename -> last_modified timestamp for all indexed files."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Ensure table exists (precautionary)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS indexed_files (
        filename TEXT PRIMARY KEY,
        last_modified REAL,
        indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("SELECT filename, last_modified FROM indexed_files")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def mark_file_indexed(filename: str, last_modified: float):
    """Saves or updates the indexing record for a file."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO indexed_files (filename, last_modified, indexed_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (filename, last_modified))
    conn.commit()
    conn.close()

def remove_indexed_file_record(filename: str):
    """Deletes the indexing record for a file."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM indexed_files WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()

def delete_document_by_title_prefix(title_prefix: str):
    """Deletes all document chunks whose title starts with title_prefix."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM documents WHERE title LIKE ? AND category = 'document'",
        (title_prefix + "%",)
    )
    conn.commit()
    conn.close()


def add_document(title: str, content: str, category: str, embedding: List[float] = None) -> int:
    """Inserts a new document chunk into SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    embedding_str = json.dumps(embedding) if embedding else None
    
    cursor.execute(
        "INSERT INTO documents (title, content, category, embedding) VALUES (?, ?, ?, ?)",
        (title, content, category, embedding_str)
    )
    doc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doc_id

def delete_document(doc_id: int):
    """Deletes a document from the database by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

def get_all_documents() -> List[Dict[str, Any]]:
    """Returns a list of all documents, ordered by creation time."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, category, created_at FROM documents ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def search_similar_documents(query_embedding: List[float], limit: int = 5, category: str = None) -> List[Dict[str, Any]]:
    """Performs cosine similarity search using NumPy over SQLite data."""
    if not query_embedding:
        return []
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if category:
        cursor.execute(
            "SELECT id, title, content, category, embedding, created_at FROM documents WHERE category = ? AND embedding IS NOT NULL", 
            (category,)
        )
    else:
        cursor.execute("SELECT id, title, content, category, embedding, created_at FROM documents WHERE embedding IS NOT NULL")
        
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return []
        
    query_vec = np.array(query_embedding, dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)
    
    if query_norm == 0:
        return []
        
    results = []
    for row in rows:
        try:
            db_embedding = json.loads(row['embedding'])
            db_vec = np.array(db_embedding, dtype=np.float32)
            db_norm = np.linalg.norm(db_vec)
            
            if db_norm == 0:
                score = 0.0
            else:
                score = np.dot(query_vec, db_vec) / (query_norm * db_norm)
                
            results.append({
                "id": row["id"],
                "title": row["title"],
                "content": row["content"],
                "category": row["category"],
                "score": float(score),
                "created_at": row["created_at"]
            })
        except Exception:
            continue
            
    # Sort results by similarity score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]

# Chat history management
def save_chat_message(session_id: str, role: str, message: str):
    """Saves a single chat message (user or assistant) for streamlit session persistence."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_sessions (session_id, role, message) VALUES (?, ?, ?)",
        (session_id, role, message)
    )
    conn.commit()
    conn.close()

def get_chat_history(session_id: str) -> List[Dict[str, Any]]:
    """Retrieves chat messages for a specific session."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT role, message, created_at FROM chat_sessions WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_chat_history(session_id: str):
    """Deletes all chat messages for a session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

# User Management Functions
import hashlib

def hash_password(password: str) -> str:
    """Hashes a password using SHA-256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def create_user(username: str, password: str, role: str = 'user') -> bool:
    """Creates a new user with hashed password. Returns False if user already exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure users table exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    password_hash = hash_password(password)
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username.strip(), password_hash, role)
        )
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def verify_user(username: str, password: str) -> bool:
    """Verifies user credentials. Returns True if password matches."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False
        
    return row['password_hash'] == hash_password(password)

def get_all_users() -> List[Dict[str, Any]]:
    """Retrieves all users in the system."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY username ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_user(username: str) -> bool:
    """Deletes a user from the system."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return True

