# Five Flowers QR

Render Web Service settings:

Build Command:
`pip install -r requirements.txt`

Start Command:
`gunicorn app:app`

Environment variables:
- `DATABASE_URL`: copy the Internal Database URL from your existing Render PostgreSQL database
- `ADMIN_PASSWORD`: `fiveflowers123`
- `SECRET_KEY`: any long random text
