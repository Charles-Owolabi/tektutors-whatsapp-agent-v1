from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("sqlite://"):
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

connect_args = {}
if "sqlite" in db_url:
    connect_args = {"check_same_thread": False}
    engine_args = {
        "connect_args": connect_args,
        "future": True
    }
else:
    # Clean sslmode from query string if present because asyncpg doesn't accept sslmode as a URL query param
    parsed = urlparse(db_url)
    query_params = parse_qs(parsed.query)
    if "sslmode" in query_params:
        sslmode_val = query_params.pop("sslmode")[0]
        if sslmode_val in ("require", "verify-ca", "verify-full"):
            connect_args["ssl"] = True
        elif sslmode_val == "disable":
            connect_args["ssl"] = False
        new_query = urlencode(query_params, doseq=True)
        db_url = urlunparse(parsed._replace(query=new_query))

    engine_args = {
        "connect_args": connect_args,
        "future": True,
        "pool_size": 10,
        "max_overflow": 5,
        "pool_recycle": 1800,
        "pool_pre_ping": True
    }

engine = create_async_engine(
    db_url,
    echo=False,
    **engine_args
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
