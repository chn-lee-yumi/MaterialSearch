from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, String, BINARY, Integer, DateTime
from enum import IntEnum


class FileType(IntEnum):
    Image = 1
    Video = 2


db = SQLAlchemy()


class File(db.Model):
    id = Column(Integer, primary_key=True)
    type = Column(Integer, index=True)  # 文件类型，FileType
    # name = Column(String(255), index=True)  # 文件名
    path = Column(String(4096), index=True)  # 文件路径
    modify_time = Column(DateTime)  # 文件修改时间
    features = Column(BINARY)  # 文件预处理后的二进制数据


class Cache(db.Model):
    id = Column(String(40), primary_key=True, index=True)  # hash。如果是文字搜索，则是搜索词的hash；如果是图片搜索，则是图片的hash
    result = Column(BINARY)  # 搜索结果
