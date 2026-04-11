"""
Supabase client — FacturAI Backend
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(override=True)


def get_supabase() -> Client:
    """Cliente con service_role — bypasea RLS, para operaciones admin y auth."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def get_supabase_anon() -> Client:
    """Cliente con clave anon — para operaciones en nombre del usuario."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)
