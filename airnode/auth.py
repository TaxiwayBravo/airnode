"""Single-owner authentication with persistent, hashed sessions and scrypt passwords."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

class Auth:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS owner (id INTEGER PRIMARY KEY CHECK(id=1), salt TEXT, hash TEXT);
                CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, csrf TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS attempts (ip TEXT PRIMARY KEY, count INTEGER, until REAL);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            with db:
                yield db
        finally:
            db.close()

    def configured(self):
        with self.db() as db:
            return db.execute("SELECT 1 FROM owner").fetchone() is not None

    @staticmethod
    def hash(password, salt):
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

    def password(self, password, initial=False):
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise ValueError("Password must contain 12–128 characters")
        salt = secrets.token_hex(16)
        hashed = self.hash(password, salt)
        with self.db() as db:
            if initial:
                try:
                    db.execute("INSERT INTO owner VALUES (1,?,?)", (salt, hashed))
                except sqlite3.IntegrityError:
                    raise ValueError("Already configured") from None
            else:
                db.execute("UPDATE owner SET salt=?,hash=? WHERE id=1", (salt, hashed))
            db.execute("DELETE FROM sessions")

    def verify(self, password):
        if not isinstance(password, str) or len(password) > 128:
            return False
        with self.db() as db:
            row = db.execute("SELECT salt,hash FROM owner WHERE id=1").fetchone()
        return bool(row and hmac.compare_digest(self.hash(password, row[0]), row[1]))

    def throttle(self, ip):
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM attempts WHERE until<?", (now,))
            row = db.execute("SELECT count FROM attempts WHERE ip=?", (ip,)).fetchone()
            if row and row[0] >= 8:
                return False
            db.execute("INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(ip) DO UPDATE SET count=count+1", (ip, now + 300))
        return True

    def session(self):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), csrf, time.time() + 28800))
        return token, csrf

    def lookup(self, token):
        with self.db() as db:
            row = db.execute("SELECT csrf FROM sessions WHERE token=? AND expires>?", (digest(token), time.time())).fetchone()
        return row[0] if row else None

    def logout(self, token):
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (digest(token),))
