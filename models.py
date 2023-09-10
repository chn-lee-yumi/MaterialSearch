from sqlalchemy import BINARY, Column, DateTime, Integer, String
from sqlalchemy.ext.declarative import declarative_base

from database import engine

BaseModel = declarative_base()


def create_tables():
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
