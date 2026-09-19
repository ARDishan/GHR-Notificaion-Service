"""
db.py
------------------------------------------------------------
Shared Postgres connection helper.

Copy this file into BOTH project folders:
    - Payment Schedule Statement Generator
    - Customer Notification Service

Both apps point at the SAME database using the same env vars,
so put the same .env values (or the same secrets) in each folder:

    DB_HOST=your-db-host.cloud
    DB_PORT=5432
    DB_NAME=your_db
    DB_USER=your_user
    DB_PASSWORD=your_password
    DB_SSLMODE=require
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()

_engine = None


def get_engine():
    """
    Return a cached SQLAlchemy engine connected to the shared Postgres DB
    (Supabase).
    """

    global _engine

    if _engine is not None:
        return _engine

    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    sslmode = os.getenv("DB_SSLMODE", "").strip()

    missing = [
        name
        for name, value in [
            ("DB_HOST", host),
            ("DB_NAME", dbname),
            ("DB_USER", user),
            ("DB_PASSWORD", password),
        ]
        if not value
    ]

    if missing:
        raise ValueError(
            "Missing database environment variable(s): "
            + ", ".join(missing)
            + ". Set them in your .env file."
        )

    # URL.create percent-encodes user/password automatically, so special
    # characters in your password (@, $, :, /, # etc.) can't corrupt the
    # connection string the way manual string-formatting would.
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=dbname,
        query={"sslmode": sslmode} if sslmode else {},
    )

    _engine = create_engine(url, pool_pre_ping=True)

    return _engine