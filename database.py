from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, String, BINARY, Integer, DateTime

db = SQLAlchemy()


class Image(db.Model):
    id = Column(Integer, primary_key=True)
    path = Column(String(4096), index=True)  # 文件路径
    modify_time = Column(DateTime)  # 文件修改时间
    features = Column(BINARY)  # 文件预处理后的二进制数据


class Video(db.Model):
    id = Column(Integer, primary_key=True)
    path = Column(String(4096), index=True)  # 文件路径
    frame_time = Column(Integer, index=True)  # 这一帧所在的时间
    modify_time = Column(DateTime)  # 文件修改时间
    features = Column(BINARY)  # 文件预处理后的二进制数据


class Cache(db.Model):
    id = Column(String(40), primary_key=True, index=True)  # hash。如果是文字搜索，则是搜索词的hash；如果是图片搜索，则是图片的hash
    result = Column(BINARY)  # 搜索结果
