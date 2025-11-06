import os
import datetime

from sqlalchemy import BINARY, Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from config import SQLALCHEMY_DATABASE_URL

# 数据库目录不存在的时候自动创建目录。TODO：如果是mysql之类的数据库，这里的代码估计是不兼容的
folder_path = os.path.dirname(SQLALCHEMY_DATABASE_URL.replace("sqlite:///", ""))
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

# 本地扫描数据库
BaseModel = declarative_base()
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
DatabaseSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# PexelsVideo数据库
BaseModelPexelsVideo = declarative_base()
engine_pexels_video = create_engine(
    'sqlite:///./PexelsVideo.db',
    connect_args={"check_same_thread": False}
)
DatabaseSessionPexelsVideo = sessionmaker(autocommit=False, autoflush=False, bind=engine_pexels_video)


def create_tables():
    """
    创建数据库表
    """
    BaseModel.metadata.create_all(bind=engine)
    BaseModelPexelsVideo.metadata.create_all(bind=engine_pexels_video)


class Image(BaseModel):
    __tablename__ = "image"
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String(4096), index=True)  # 文件路径
    modify_time = Column(DateTime, index=True)  # 文件修改时间
    features = Column(BINARY)  # 文件预处理后的二进制数据
    checksum = Column(String(40), index=True)  # 文件SHA1

    # 文件属性
    width = Column(Integer)  # 图片宽度
    height = Column(Integer)  # 图片高度
    aspect_ratio = Column(Float, index=True)  # 宽高比（精确值）
    aspect_ratio_standard = Column(String(16), index=True)  # 标准宽高比（如 16:9, 4:3）
    file_size = Column(Integer)  # 文件大小（字节）
    file_format = Column(String(16))  # 文件格式（jpg, png等）

    # 时间戳
    upload_time = Column(DateTime, default=datetime.datetime.now)  # 上传时间
    last_accessed = Column(DateTime)  # 最后访问时间

    # 分类标签
    category = Column(String(64), index=True)  # 主分类（如：建筑外观、室内设计）
    sub_category = Column(String(64))  # 子分类
    tags = Column(Text)  # 标签（JSON 数组）
    building_type = Column(String(64))  # 建筑类型（住宅、商业、办公等）
    design_style = Column(String(64), index=True)  # 设计风格（现代、古典等）

    # 来源信息
    source_type = Column(String(32), default='local')  # 来源类型（local, project_archive, web等）
    source_project = Column(String(128))  # 来源项目ID（如果是从项目归档而来）
    source_notes = Column(Text)  # 来源备注

    # 质量管理
    quality_score = Column(Float)  # 质量评分（0-100）
    is_featured = Column(Boolean, default=False)  # 是否为精选素材

    # 去重预留
    phash = Column(String(64), index=True)  # 感知哈希（用于去重）
    duplicate_group = Column(String(64))  # 重复组ID
    is_duplicate = Column(Boolean, default=False)  # 是否为重复图片

    # AI 增强
    ai_description = Column(Text)  # AI 生成的图片描述
    ai_description_vector = Column(BINARY)  # AI 描述的向量特征

    # 软删除
    is_deleted = Column(Boolean, default=False, index=True)  # 软删除标记
    deleted_time = Column(DateTime)  # 删除时间


class Video(BaseModel):
    __tablename__ = "video"
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String(4096), index=True)  # 文件路径
    frame_time = Column(Integer)  # 这一帧所在的时间
    modify_time = Column(DateTime, index=True)  # 文件修改时间
    features = Column(BINARY)  # 文件预处理后的二进制数据
    checksum = Column(String(40), index=True)  # 文件SHA1

    # 文件属性
    width = Column(Integer)  # 视频宽度
    height = Column(Integer)  # 视频高度
    aspect_ratio = Column(Float, index=True)  # 宽高比
    duration = Column(Integer)  # 视频时长（秒）
    file_size = Column(Integer)  # 文件大小（字节）
    file_format = Column(String(16))  # 文件格式（mp4, mov等）

    # 时间戳
    upload_time = Column(DateTime, default=datetime.datetime.now)  # 上传时间
    last_accessed = Column(DateTime)  # 最后访问时间

    # 分类标签
    category = Column(String(64), index=True)  # 主分类
    sub_category = Column(String(64))  # 子分类
    tags = Column(Text)  # 标签（JSON 数组）
    building_type = Column(String(64))  # 建筑类型
    design_style = Column(String(64), index=True)  # 设计风格

    # 来源信息
    source_type = Column(String(32), default='local')  # 来源类型
    source_project = Column(String(128))  # 来源项目ID
    source_notes = Column(Text)  # 来源备注

    # 质量管理
    quality_score = Column(Float)  # 质量评分
    is_featured = Column(Boolean, default=False)  # 是否为精选素材

    # AI 增强
    ai_description = Column(Text)  # AI 生成的视频描述
    ai_description_vector = Column(BINARY)  # AI 描述的向量特征

    # 软删除
    is_deleted = Column(Boolean, default=False, index=True)  # 软删除标记
    deleted_time = Column(DateTime)  # 删除时间


class PexelsVideo(BaseModelPexelsVideo):
    __tablename__ = "PexelsVideo"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(128))  # 标题
    description = Column(String(256))  # 视频描述
    duration = Column(Integer, index=True)  # 视频时长，单位秒
    view_count = Column(Integer, index=True)  # 视频播放量
    thumbnail_loc = Column(String(256))  # 视频缩略图链接
    content_loc = Column(String(256))  # 视频链接
    thumbnail_feature = Column(BINARY)  # 视频缩略图特征


class Project(BaseModel):
    """项目模型 - 存储在 projects_metadata.db 中"""
    __tablename__ = "project"
    id = Column(String(128), primary_key=True, index=True)  # 项目ID（如 proj_2025_万科_01）
    name = Column(String(256), nullable=False, index=True)  # 项目名称
    client_name = Column(String(256))  # 客户名称
    description = Column(Text)  # 项目描述
    status = Column(String(32), default='active', index=True)  # 项目状态：active/completed/archived
    created_time = Column(DateTime, default=datetime.datetime.now)  # 创建时间
    updated_time = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)  # 更新时间
    image_count = Column(Integer, default=0)  # 图片数量
    video_count = Column(Integer, default=0)  # 视频数量
    total_size = Column(Integer, default=0)  # 总大小（字节）
    database_path = Column(String(1024))  # 数据库文件路径
    is_deleted = Column(Boolean, default=False)  # 软删除标记


# 项目数据库的基类（用于 proj_*.db）
BaseModelProject = declarative_base()


class ProjectImage(BaseModelProject):
    """项目图片模型 - 存储在各项目数据库 proj_*.db 中"""
    __tablename__ = "image"
    # 基础字段（与 Image 相同）
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String(4096), index=True)
    modify_time = Column(DateTime, index=True)
    features = Column(BINARY)
    checksum = Column(String(40), index=True)

    # 文件属性
    width = Column(Integer)
    height = Column(Integer)
    aspect_ratio = Column(Float, index=True)
    aspect_ratio_standard = Column(String(16), index=True)
    file_size = Column(Integer)
    file_format = Column(String(16))

    # 时间戳
    upload_time = Column(DateTime, default=datetime.datetime.now)
    last_accessed = Column(DateTime)

    # 分类标签
    category = Column(String(64), index=True)
    sub_category = Column(String(64))
    tags = Column(Text)
    building_type = Column(String(64))
    design_style = Column(String(64), index=True)

    # 来源信息
    source_type = Column(String(32), default='local')
    source_project = Column(String(128))
    source_notes = Column(Text)

    # 质量管理
    quality_score = Column(Float)
    is_featured = Column(Boolean, default=False)

    # 去重预留
    phash = Column(String(64), index=True)
    duplicate_group = Column(String(64))
    is_duplicate = Column(Boolean, default=False)

    # AI 增强
    ai_description = Column(Text)
    ai_description_vector = Column(BINARY)

    # 软删除
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_time = Column(DateTime)

    # 项目特有字段
    image_type = Column(String(32), index=True)  # 图片类型（效果图、实景图、参考图等）
    stage = Column(String(32))  # 项目阶段（方案、初设、施工图等）
    space_type = Column(String(64))  # 空间类型（客厅、卧室、外立面等）

    # 版本管理
    version = Column(Integer, default=1)  # 版本号
    parent_id = Column(Integer)  # 父版本ID

    # 审批流程
    is_approved = Column(Boolean, default=False)  # 是否已审批
    approved_by = Column(String(128))  # 审批人
    approved_time = Column(DateTime)  # 审批时间

    # 归档状态
    archived = Column(Boolean, default=False, index=True)  # 是否已归档到永久库
    archived_to_id = Column(Integer)  # 归档到永久库的记录ID
    archived_time = Column(DateTime)  # 归档时间


class ProjectVideo(BaseModelProject):
    """项目视频模型 - 存储在各项目数据库 proj_*.db 中"""
    __tablename__ = "video"
    # 基础字段（与 Video 相同）
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String(4096), index=True)
    frame_time = Column(Integer)
    modify_time = Column(DateTime, index=True)
    features = Column(BINARY)
    checksum = Column(String(40), index=True)

    # 文件属性
    width = Column(Integer)
    height = Column(Integer)
    aspect_ratio = Column(Float, index=True)
    duration = Column(Integer)
    file_size = Column(Integer)
    file_format = Column(String(16))

    # 时间戳
    upload_time = Column(DateTime, default=datetime.datetime.now)
    last_accessed = Column(DateTime)

    # 分类标签
    category = Column(String(64), index=True)
    sub_category = Column(String(64))
    tags = Column(Text)
    building_type = Column(String(64))
    design_style = Column(String(64), index=True)

    # 来源信息
    source_type = Column(String(32), default='local')
    source_project = Column(String(128))
    source_notes = Column(Text)

    # 质量管理
    quality_score = Column(Float)
    is_featured = Column(Boolean, default=False)

    # AI 增强
    ai_description = Column(Text)
    ai_description_vector = Column(BINARY)

    # 软删除
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_time = Column(DateTime)

    # 项目特有字段
    video_type = Column(String(32), index=True)  # 视频类型（动画、实拍等）
    stage = Column(String(32))  # 项目阶段
    space_type = Column(String(64))  # 空间类型

    # 版本管理
    version = Column(Integer, default=1)
    parent_id = Column(Integer)

    # 审批流程
    is_approved = Column(Boolean, default=False)
    approved_by = Column(String(128))
    approved_time = Column(DateTime)

    # 归档状态
    archived = Column(Boolean, default=False, index=True)
    archived_to_id = Column(Integer)
    archived_time = Column(DateTime)
