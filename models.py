import os

from sqlalchemy import BINARY, Column, DateTime, Integer, String
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from config import SQLALCHEMY_DATABASE_URL

# 数据库目录不存在的时候自动创建目录。TODO：如果是mysql之类的数据库，这里的代码估计是不兼容的
folder_path = os.path.dirname(SQLALCHEMY_DATABASE_URL.replace("sqlite:///", ""))
if not os.path.exists(folder_path):
    os.makedirs(folder_path)
BaseModel = declarative_base()

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

DatabaseSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """
    创建数据库表
    """
    BaseModel.metadata.create_all(bind=engine)


class Image(BaseModel):
    __tablename__ = "image"
    id = Column(Integer, primary_key=True)
    path = Column(String(4096), index=True)  # 文件路径
    modify_time = Column(DateTime)  # 文件修改时间
    features = Column(BINARY)  # 文件预处理后的二进制数据


class Video(BaseModel):
    __tablename__ = "video"
    id = Column(Integer, primary_key=True)
    path = Column(String(4096), index=True)  # 文件路径
    frame_time = Column(Integer, index=True)  # 这一帧所在的时间
    modify_time = Column(DateTime)  # 文件修改时间
    features = Column(BINARY)  # 文件预处理后的二进制数据