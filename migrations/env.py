from alembic import context
from sqlalchemy import create_engine

from legalrag.config import database_url

# SQLAlchemy needs the driver in the URL; the rest of the code uses the plain postgresql:// form.
url = context.config.attributes.get("url") or database_url()
url = url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(url)
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
