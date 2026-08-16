from sqlalchemy import create_engine

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    
    echo=settings.SQL_ECHO,
    future=True,
    pool_pre_ping=True
)