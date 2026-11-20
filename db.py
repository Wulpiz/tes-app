"""Koneksi ke MySQL db_dapur dengan auto-inisialisasi database."""
import os

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import pooling

load_dotenv()

_pool = None
_sudah_init = False


def init_db():
    """Otomatis membuat database, mengimpor db_dapur.sql, dan menyesuaikan kolom UI jika belum ada."""
    global _sudah_init
    if _sudah_init:
        return

    host = os.getenv("DB_HOST", "localhost")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    db_name = os.getenv("DB_NAME", "db_dapur")

    # 1. Koneksi ke server MySQL tanpa menentukan database untuk membuat DB jika belum ada
    conn = mysql.connector.connect(host=host, user=user, password=password)
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
        )
        cur.execute(f"USE `{db_name}`")

        # 2. Cek apakah tabel recipes sudah ada; jika belum, impor otomatis dari db_dapur.sql
        cur.execute("SHOW TABLES LIKE 'recipes'")
        if not cur.fetchone():
            sql_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_dapur.sql")
            if os.path.isfile(sql_path):
                with open(sql_path, "r", encoding="utf-8") as f:
                    sql_script = f.read()
                for statement in sql_script.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        cur.execute(stmt)

        # 3. Pastikan kolom tambahan UI (foto, favorit, warna) tersedia di tabel recipes
        cur.execute("SHOW COLUMNS FROM `recipes`")
        kolom_ada = {row[0] for row in cur.fetchall()}
        if "foto" not in kolom_ada:
            cur.execute("ALTER TABLE `recipes` ADD COLUMN `foto` VARCHAR(255) DEFAULT ''")
        if "favorit" not in kolom_ada:
            cur.execute("ALTER TABLE `recipes` ADD COLUMN `favorit` TINYINT(1) DEFAULT 0")
        if "warna" not in kolom_ada:
            cur.execute("ALTER TABLE `recipes` ADD COLUMN `warna` VARCHAR(20) DEFAULT '#E2AE58'")

        conn.commit()
        _sudah_init = True
    finally:
        cur.close()
        conn.close()


def get_pool():
    global _pool
    init_db()  # Jalankan pengecekan & auto-import sebelum pool dibuat
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="dapur_pool",
            pool_size=5,
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "db_dapur"),
        )
    return _pool


def get_db():
    """Dependency FastAPI: satu koneksi per request, otomatis dikembalikan ke pool."""
    conn = get_pool().get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(conn, sql, params=(), one=False):
    """SELECT -> list of dict (atau satu dict / None kalau one=True)."""
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()
    finally:
        cur.close()


def execute(conn, sql, params=()):
    """INSERT/UPDATE/DELETE -> mengembalikan lastrowid. Commit dilakukan di pemanggil."""
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return cur.lastrowid
    finally:
        cur.close()


def execute_many(conn, sql, rows):
    cur = conn.cursor()
    try:
        cur.executemany(sql, rows)
    finally:
        cur.close()