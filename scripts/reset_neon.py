import os
import sys
from pathlib import Path
import environ
import psycopg2

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

DB_NAME = env('DATABASE_NAME')
DB_USER = env('DATABASE_USER')
DB_PASS = env('DATABASE_PASS')
DB_HOST = env('DATABASE_HOST')
DB_PORT = env('DATABASE_PORT', default='5432')
DB_SSLMODE = env('DATABASE_SSLMODE', default='require')

print('Conectando a Neon en', DB_HOST)

dsn = f"dbname={DB_NAME} user={DB_USER} password={DB_PASS} host={DB_HOST} port={DB_PORT} sslmode={DB_SSLMODE}"

try:
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    print('Ejecutando DROP SCHEMA public CASCADE;')
    cur.execute('DROP SCHEMA public CASCADE;')
    print('DROP OK — recreando schema public')
    cur.execute('CREATE SCHEMA public;')
    print('Schema public recreado con éxito.')
    cur.close()
    conn.close()
except Exception as e:
    print('Error al resetear Neon:', e)
    sys.exit(1)

print('Reset completado.')
