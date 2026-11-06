"""WSGI entry point: `flask --app wsgi run` for development, `gunicorn wsgi:app` for deployment."""
from app import create_app

app = create_app()
