import datetime
import logging
import os

from sqlalchemy import asc
from sqlalchemy.orm import Session

from models import Image, Video, PexelsVideo

logger = logging.getLogger(__name__)


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


def delete_image_if_outdated(session: Session, path: str) -> bool:
    """
    判断图片是否修改，若修改则删除
    :param session: Session, 数据库 session
    :param path: str, 图片路径
    :return: bool, 若文件未修改返回 True
    """
    record = session.query(Image).filter_by(path=path).first()
    if not record:
        return False
    modify_time = os.path.getmtime(path)
    modify_time = datetime.datetime.fromtimestamp(modify_time)
    if record.modify_time == modify_time:
        logger.debug(f"文件无变更，跳过：{path}")
        return True
    logger.info(f"文件有更新：{path}")
    session.delete(record)
    session.commit()
    return False


def delete_video_if_outdated(session: Session, path: str) -> bool:
    """
    判断视频是否修改，若修改则删除
    :param session: Session, 数据库 session
    :param path: str, 视频路径
    :return: bool, 若文件未修改返回 True
    """
    record = session.query(Video).filter_by(path=path).first()
    if not record:
        return False
    modify_time = os.path.getmtime(path)
    modify_time = datetime.datetime.fromtimestamp(modify_time)
    if record.modify_time == modify_time:
        logger.debug(f"文件无变更，跳过：{path}")
        return True
    logger.info(f"文件有更新：{path}")
    session.query(Video).filter_by(path=path).delete()
    session.commit()
    return False


def get_video_paths(session: Session):
    """获取所有视频的路径"""
    for i, in session.query(Video.path).distinct():
        yield i


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


def add_image(session: Session, path: str, modify_time: datetime.datetime, features: bytes):
    """添加图片到数据库"""
    logger.info(f"新增文件：{path}")
    image = Image(path=path, modify_time=modify_time, features=features)
    session.add(image)
    session.commit()


def add_video(session: Session, path: str, modify_time, frame_time_features_generator):
    """
    将处理后的视频数据入库
    :param session: Session, 数据库session
    :param path: str, 视频路径
    :param modify_time: datetime, 文件修改时间
    :param frame_time_features_generator: 返回(帧序列号,特征)元组的迭代器
    """
    # 使用 bulk_save_objects 一次性提交，因此处理至一半中断不会导致下次扫描时跳过
    logger.info(f"新增文件：{path}")
    video_list = (
        Video(
            path=path, modify_time=modify_time, frame_time=frame_time, features=features
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
