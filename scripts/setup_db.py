import os
import asyncio
import asyncpg
from sqlalchemy import create_engine
from backend.config import DATABASE_URL, PGDATABASE, PGUSER, PGPASSWORD, PGHOST, PGPORT
import logging
from backend.db.models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("setup_db")

async def setup_database():
    logger.info("Starting database setup...")

    # We first connect to the default 'postgres' database to create our target database
    # Construct postgres connection URL
    sys_url = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/postgres"

    try:
        sys_conn = await asyncpg.connect(sys_url)
    except Exception as e:
        logger.error(f"Failed to connect to postgres system database: {e}")
        return

    try:
        # Check if database exists
        db_exists = await sys_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", PGDATABASE
        )

        if not db_exists:
            logger.info(f"Creating database {PGDATABASE}...")
            await sys_conn.execute(f'CREATE DATABASE "{PGDATABASE}"')
            logger.info(f"Database {PGDATABASE} created successfully.")
        else:
            logger.info(f"Database {PGDATABASE} already exists.")
    except Exception as e:
        logger.error(f"Error checking/creating database: {e}")
    finally:
        await sys_conn.close()

    # Connect to the target database to install extensions
    target_url = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{PGDATABASE}"
    try:
        target_conn = await asyncpg.connect(target_url)
        logger.info("Installing extensions (uuid-ossp, pgcrypto)...")
        await target_conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        await target_conn.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
        logger.info("Extensions installed successfully.")
        await target_conn.close()
    except Exception as e:
        logger.error(f"Failed to install extensions: {e}")
        return

    # Apply schema
    try:
        logger.info("Applying schema via SQLAlchemy metadata.create_all...")
        # create_all needs a synchronous engine, and DATABASE_URL is usually sync
        sync_url = DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        engine = create_engine(sync_url)
        Base.metadata.create_all(engine)
        logger.info("Schema applied successfully.")
    except Exception as e:
        logger.error(f"Failed to apply schema: {e}")

if __name__ == "__main__":
    asyncio.run(setup_database())
