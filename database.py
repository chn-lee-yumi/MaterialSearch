from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import SQLALCHEMY_DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

# 起名为 SessionLocal，与 sqlalchemy 的 Session 类所区分
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
