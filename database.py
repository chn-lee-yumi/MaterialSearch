import datetime
import logging
import os
from typing import Optional, Dict

from sqlalchemy import asc, create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Image, Video, PexelsVideo, Project, ProjectImage, ProjectVideo, BaseModel, BaseModelProject

logger = logging.getLogger(__name__)


class ProjectDatabaseManager:
    """
    多数据库管理器
    管理永久库、项目元信息库、以及多个项目数据库的连接
    """

    def __init__(self,
                 permanent_db_path: str = './instance/permanent.db',
                 metadata_db_path: str = './instance/projects_metadata.db',
                 project_db_dir: str = './instance/projects'):
        """
        初始化数据库管理器

        Args:
            permanent_db_path: 永久库数据库路径
            metadata_db_path: 项目元信息库路径
            project_db_dir: 项目数据库目录
        """
        self.permanent_db_path = permanent_db_path
        self.metadata_db_path = metadata_db_path
        self.project_db_dir = project_db_dir

        # 确保目录存在
        os.makedirs(os.path.dirname(permanent_db_path), exist_ok=True)
        os.makedirs(os.path.dirname(metadata_db_path), exist_ok=True)
        os.makedirs(project_db_dir, exist_ok=True)

        # 数据库引擎和会话工厂
        self.permanent_engine = None
        self.metadata_engine = None
        self.permanent_session_factory = None
        self.metadata_session_factory = None
        self.project_engines: Dict[str, any] = {}
        self.project_session_factories: Dict[str, sessionmaker] = {}

        # 初始化永久库和元信息库
        self._init_permanent_db()
        self._init_metadata_db()

    def _create_engine_with_wal(self, db_url: str):
        """创建启用 WAL 模式的数据库引擎"""
        engine = create_engine(
            db_url,
            connect_args={
                "check_same_thread": False,
                "timeout": 30
            }
        )
        # 启用 WAL 模式
        with engine.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()
        return engine

    def _init_permanent_db(self):
        """初始化永久库"""
        db_url = f'sqlite:///{self.permanent_db_path}'
        self.permanent_engine = self._create_engine_with_wal(db_url)
        self.permanent_session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.permanent_engine
        )
        # 创建表结构
        BaseModel.metadata.create_all(bind=self.permanent_engine)
        logger.info(f"永久库已初始化: {self.permanent_db_path}")

    def _init_metadata_db(self):
        """初始化项目元信息库"""
        db_url = f'sqlite:///{self.metadata_db_path}'
        self.metadata_engine = self._create_engine_with_wal(db_url)
        self.metadata_session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.metadata_engine
        )
        # 创建表结构
        BaseModel.metadata.create_all(bind=self.metadata_engine)
        logger.info(f"项目元信息库已初始化: {self.metadata_db_path}")

    def get_permanent_session(self) -> Session:
        """获取永久库 session"""
        return self.permanent_session_factory()

    def get_metadata_session(self) -> Session:
        """获取项目元信息库 session"""
        return self.metadata_session_factory()

    def get_project_session(self, project_id: str) -> Session:
        """
        获取指定项目的 session

        Args:
            project_id: 项目ID

        Returns:
            Session: 项目数据库 session
        """
        if project_id not in self.project_session_factories:
            self._load_project_db(project_id)
        return self.project_session_factories[project_id]()

    def _load_project_db(self, project_id: str):
        """加载项目数据库"""
        db_path = os.path.join(self.project_db_dir, f'{project_id}.db')
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"项目数据库不存在: {db_path}")

        db_url = f'sqlite:///{db_path}'
        engine = self._create_engine_with_wal(db_url)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        self.project_engines[project_id] = engine
        self.project_session_factories[project_id] = session_factory
        logger.info(f"项目数据库已加载: {project_id}")

    def create_project_database(self, project_id: str) -> str:
        """
        创建项目数据库

        Args:
            project_id: 项目ID

        Returns:
            str: 数据库文件路径
        """
        db_path = os.path.join(self.project_db_dir, f'{project_id}.db')
        if os.path.exists(db_path):
            logger.warning(f"项目数据库已存在: {db_path}")
            return db_path

        db_url = f'sqlite:///{db_path}'
        engine = self._create_engine_with_wal(db_url)

        # 创建表结构
        BaseModelProject.metadata.create_all(bind=engine)

        # 缓存连接
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.project_engines[project_id] = engine
        self.project_session_factories[project_id] = session_factory

        logger.info(f"项目数据库已创建: {db_path}")
        return db_path

    def close_project_db(self, project_id: str):
        """关闭项目数据库连接"""
        if project_id in self.project_engines:
            self.project_engines[project_id].dispose()
            del self.project_engines[project_id]
            del self.project_session_factories[project_id]
            logger.info(f"项目数据库连接已关闭: {project_id}")

    def close_all(self):
        """关闭所有数据库连接"""
        if self.permanent_engine:
            self.permanent_engine.dispose()
        if self.metadata_engine:
            self.metadata_engine.dispose()
        for engine in self.project_engines.values():
            engine.dispose()
        logger.info("所有数据库连接已关闭")


# 全局数据库管理器实例
db_manager: Optional[ProjectDatabaseManager] = None


def init_database_manager(**kwargs):
    """初始化全局数据库管理器"""
    global db_manager
    db_manager = ProjectDatabaseManager(**kwargs)
    return db_manager


def get_db_manager() -> ProjectDatabaseManager:
    """获取全局数据库管理器"""
    global db_manager
    if db_manager is None:
        db_manager = ProjectDatabaseManager()
    return db_manager


def get_image_features_by_id(session: Session, image_id: int):
    """
    返回id对应的图片feature
    """
    features = session.query(Image.features).filter_by(id=image_id).first()
    if not features:
        logger.warning("用数据库的图来进行搜索，但id在数据库中不存在")
        return None
    return features[0]


def get_image_path_by_id(session: Session, id: int):
    """
    返回id对应的图片路径
    """
    path = session.query(Image.path).filter_by(id=id).first()
    if not path:
        return None
    return path[0]


def get_image_count(session: Session):
    """获取图片总数"""
    return session.query(Image).count()


def delete_image_if_outdated(session: Session, path: str, modify_time: datetime.datetime, checksum: str = None) -> bool:
    """
    判断图片是否修改，若修改则删除
    :param session: Session, 数据库 session
    :param path: str, 图片路径
    :param modify_time: datetime.datetime, 图片修改时间
    :param checksum: str, 图片hash
    :return: bool, 若文件未修改返回 True
    """
    record = session.query(Image).filter_by(path=path).first()
    if not record:
        return False
    # 如果有checksum，则判断checksum
    if checksum and record.checksum:
        if record.checksum == checksum:
            logger.debug(f"文件无变更，跳过：{path}")
            return True
    else:  # 否则判断modify_time
        if record.modify_time == modify_time:
            logger.debug(f"文件无变更，跳过：{path}")
            return True
    logger.info(f"文件有更新：{path}")
    session.delete(record)
    session.commit()
    return False


def delete_video_if_outdated(session: Session, path: str, modify_time: datetime.datetime, checksum: str = None) -> bool:
    """
    判断视频是否修改，若修改则删除
    :param session: Session, 数据库 session
    :param path: str, 视频路径
    :param modify_time: datetime.datetime, 视频修改时间
    :param checksum: str, 视频hash
    :return: bool, 若文件未修改返回 True
    """
    record = session.query(Video).filter_by(path=path).first()
    if not record:
        return False
    # 如果有checksum，则判断checksum
    if checksum and record.checksum:
        if record.checksum == checksum:
            logger.debug(f"文件无变更，跳过：{path}")
            return True
    else:  # 否则判断modify_time
        if record.modify_time == modify_time:
            logger.debug(f"文件无变更，跳过：{path}")
            return True
    logger.info(f"文件有更新：{path}")
    session.query(Video).filter_by(path=path).delete()
    session.commit()
    return False


def get_video_paths(session: Session, filter_path: str = None, start_time: int = None, end_time: int = None):
    """获取所有视频的路径，支持通过路径和修改时间筛选"""
    query = session.query(Video.path, Video.modify_time).distinct()
    if filter_path:
        query = query.filter(Video.path.like("%" + filter_path + "%"))
    if start_time:
        query = query.filter(Video.modify_time >= datetime.datetime.fromtimestamp(start_time))
    if end_time:
        query = query.filter(Video.modify_time <= datetime.datetime.fromtimestamp(end_time))
    for path, modify_time in query:
        yield path


def get_frame_times_features_by_path(session: Session, path: str):
    """获取路径对应视频的features"""
    l = (
        session.query(Video.frame_time, Video.features)
        .filter_by(path=path)
        .order_by(Video.frame_time)
        .all()
    )
    frame_times, features = zip(*l)
    return frame_times, features


def get_video_count(session: Session):
    """获取视频总数"""
    return session.query(Video.path).distinct().count()


def get_pexels_video_count(session: Session):
    """获取视频总数"""
    return session.query(PexelsVideo).count()


def get_video_frame_count(session: Session):
    """获取视频帧总数"""
    return session.query(Video).count()


def delete_video_by_path(session: Session, path: str):
    """删除路径对应的视频数据"""
    session.query(Video).filter_by(path=path).delete()
    session.commit()


def add_image(session: Session, path: str, modify_time: datetime.datetime, checksum: str, features: bytes,
              width: int = None, height: int = None, aspect_ratio: float = None,
              aspect_ratio_standard: str = None, file_size: int = None, file_format: str = None,
              phash: str = None, **kwargs):
    """
    添加图片到数据库

    Args:
        session: 数据库 session
        path: 文件路径
        modify_time: 修改时间
        checksum: 文件校验和
        features: 特征向量
        width: 图片宽度
        height: 图片高度
        aspect_ratio: 宽高比
        aspect_ratio_standard: 标准宽高比
        file_size: 文件大小
        file_format: 文件格式
        phash: 感知哈希
        **kwargs: 其他字段
    """
    logger.info(f"新增文件：{path}")
    image = Image(
        path=path,
        modify_time=modify_time,
        features=features,
        checksum=checksum,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        aspect_ratio_standard=aspect_ratio_standard,
        file_size=file_size,
        file_format=file_format,
        phash=phash,
        upload_time=datetime.datetime.now()
    )
    session.add(image)
    session.commit()


def add_video(session: Session, path: str, modify_time: datetime.datetime, checksum: str, frame_time_features_generator):
    """
    将处理后的视频数据入库
    :param session: Session, 数据库session
    :param path: str, 视频路径
    :param modify_time: datetime, 文件修改时间
    :param checksum: str, 文件hash
    :param frame_time_features_generator: 返回(帧序列号,特征)元组的迭代器
    """
    # 使用 bulk_save_objects 一次性提交，因此处理至一半中断不会导致下次扫描时跳过
    logger.info(f"新增文件：{path}")
    video_list = (
        Video(
            path=path, modify_time=modify_time, frame_time=frame_time, features=features, checksum=checksum
        )
        for frame_time, features in frame_time_features_generator
    )
    session.bulk_save_objects(video_list)
    session.commit()


def add_pexels_video(session: Session, content_loc: str, duration: int, view_count: int, thumbnail_loc: str, title: str, description: str,
                     thumbnail_feature: bytes):
    """添加pexels视频到数据库"""
    pexels_video = PexelsVideo(
        content_loc=content_loc, duration=duration, view_count=view_count, thumbnail_loc=thumbnail_loc, title=title, description=description,
        thumbnail_feature=thumbnail_feature
    )
    session.add(pexels_video)
    session.commit()


def delete_record_if_not_exist(session: Session, assets: set):
    """
    删除不存在于 assets 集合中的图片 / 视频的数据库记录
    """
    for file in session.query(Image):
        if file.path not in assets:
            logger.info(f"文件已删除：{file.path}")
            session.delete(file)
    for path in session.query(Video.path).distinct():
        path = path[0]
        if path not in assets:
            logger.info(f"文件已删除：{path}")
            session.query(Video).filter_by(path=path).delete()
    session.commit()


def is_video_exist(session: Session, path: str):
    """判断视频是否存在"""
    video = session.query(Video).filter_by(path=path).first()
    if video:
        return True
    return False


def is_pexels_video_exist(session: Session, thumbnail_loc: str):
    """判断pexels视频是否存在"""
    video = session.query(PexelsVideo).filter_by(thumbnail_loc=thumbnail_loc).first()
    if video:
        return True
    return False


def get_image_id_path_features(session: Session) -> tuple[list[int], list[str], list[bytes]]:
    """
    获取全部图片的 id, 路径, 特征，返回三个列表
    """
    session.query(Image).filter(Image.features.is_(None)).delete()
    session.commit()
    query = session.query(Image.id, Image.path, Image.features)
    try:
        id_list, path_list, features_list = zip(*query)
        return id_list, path_list, features_list
    except ValueError:  # 解包失败
        return [], [], []


def get_image_id_path_features_filter_by_path_time(session: Session, path: str, start_time: int, end_time: int) -> tuple[
    list[int], list[str], list[bytes]]:
    """
    根据路径和时间，筛选出对应图片的 id, 路径, 特征，返回三个列表
    """
    session.query(Image).filter(Image.features.is_(None)).delete()
    session.commit()
    query = session.query(Image.id, Image.path, Image.features, Image.modify_time)
    if start_time:
        query = query.filter(Image.modify_time >= datetime.datetime.fromtimestamp(start_time))
    if end_time:
        query = query.filter(Image.modify_time <= datetime.datetime.fromtimestamp(end_time))
    if path:
        query = query.filter(Image.path.like("%" + path + "%"))
    try:
        id_list, path_list, features_list, modify_time_list = zip(*query)
        return id_list, path_list, features_list
    except ValueError:  # 解包失败
        return [], [], []


def search_image_by_path(session: Session, path: str):
    """
    根据路径搜索图片
    :return: (图片id, 图片路径) 元组列表
    """
    return (
        session.query(Image.id, Image.path)
        .filter(Image.path.like("%" + path + "%"))
        .order_by(asc(Image.path))
        .all()
    )


def search_video_by_path(session: Session, path: str):
    """
    根据路径搜索视频
    """
    return (
        session.query(Video.path)
        .distinct()
        .filter(Video.path.like("%" + path + "%"))
        .order_by(asc(Video.path))
        .all()
    )


def get_pexels_video_features(session: Session):
    """返回所有pexels视频"""
    query = session.query(
        PexelsVideo.thumbnail_feature, PexelsVideo.thumbnail_loc, PexelsVideo.content_loc,
        PexelsVideo.title, PexelsVideo.description, PexelsVideo.duration, PexelsVideo.view_count
    ).all()
    try:
        thumbnail_feature_list, thumbnail_loc_list, content_loc_list, title_list, description_list, duration_list, view_count_list = zip(*query)
        return thumbnail_feature_list, thumbnail_loc_list, content_loc_list, title_list, description_list, duration_list, view_count_list
    except ValueError:  # 解包失败
        return [], [], [], [], [], [], []


def get_pexels_video_by_id(session: Session, uuid: str):
    """根据id搜索单个pexels视频"""
    return session.query(PexelsVideo).filter_by(id=uuid).first()
