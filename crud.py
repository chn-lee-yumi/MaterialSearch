import datetime
import logging
import os
import pickle
import tqdm

from sqlalchemy import asc
from sqlalchemy.orm import Session

from config import MAX_RESULT_NUM
from models import Image, Video

logger = logging.getLogger(__name__)


def check_if_optimized_database(session: Session) -> bool:
    image = session.query(Image).first()
    try:
        pickle.loads(image.features)
        return False
    except Exception as e:
        logger.debug(f"optimize_db pickle.loads: {repr(e)}")
        logger.info("数据库已经优化过")
        return True


def optimize_image(session: Session):
    i = 0
    for file in tqdm.tqdm(session.query(Image), desc='优化图像数据库'):
        features = pickle.loads(file.features)
        if features is None:
            session.delete(file)
        else:
            file.features = features.tobytes()
        i += 1
        if i % 1000 == 0:
            session.commit()
    session.commit()


def optimize_video(session: Session):
    i = 0
    for frame in tqdm.tqdm(session.query(Video), desc='优化视频数据库'):
        features = pickle.loads(frame.features)
        if features is None:
            session.delete(frame)
        else:
            frame.features = features.tobytes()
        i += 1
        if i % 1000 == 0:
            session.commit()
    session.commit()


def get_image_features_by_id(session: Session, id: int):
    features = session.query(Image.features).filter_by(id=id).first()
    if not features:
        logger.warning("用数据库的图来进行搜索，但id在数据库中不存在")
        return b""
    return features[0]


def get_image_path_by_id(session: Session, id: int):
    path = session.query(Image.path).filter_by(id=id).first()
    if path:
        return path[0]
    return ""


def get_image_count(session: Session):
    return session.query(Image).count()


def delete_image_if_outdated(
    session: Session, path: str, modify_time: datetime.datetime
) -> bool:
    """
    判断图片是否修改，若修改则删除
    :param session: Session, 数据库 session
    :param path: str, 图片路径
    :param modify_time: datetime, 文件修改时间
    :return: bool, 若文件未修改返回 True
    """
    record = session.query(Image).filter_by(path=path).first()
    if not record:
        logger.info(f"新增文件：{path}")
        return False
    modify_time = os.path.getmtime(path)
    modify_time = datetime.datetime.fromtimestamp(modify_time)
    if record.modify_time == modify_time:
        # 未修改
        logger.debug(f"文件无变更，跳过：{path}")
        return True
    logger.info(f"文件有更新：{path}")
    session.delete(record)
    session.commit()
    return False


def delete_video_if_outdated(
    session: Session, path: str, modify_time: datetime.datetime
) -> bool:
    """
    判断视频是否修改，若修改则删除
    :param session: Session, 数据库 session
    :param path: str, 视频路径
    :param modify_time: datetime, 文件修改时间
    :return: bool, 若文件未修改返回 True
    """
    record = session.query(Video).filter_by(path=path).first()
    if not record:
        logger.info(f"新增文件：{path}")
        return False
    if record.modify_time == modify_time:
        # 未修改
        logger.debug(f"文件无变更，跳过：{path}")
        return True
    logger.info(f"文件有更新：{path}")
    session.query(Video).filter_by(path=path).delete()
    session.commit()
    return False


def get_video_paths(session: Session):
    for i, in session.query(Video.path).distinct():
        yield i


def get_frame_times_features_by_path(session: Session, path: str):
    l = (
        session.query(Video.frame_time, Video.features)
        .filter_by(path=path)
        .order_by(Video.frame_time)
        .all()
    )
    frame_times, features = zip(*l)
    return frame_times, features


def get_video_count(session: Session):
    return session.query(Video.path).distinct().count()


def get_video_frame_count(session: Session):
    return session.query(Video).count()


def delete_video_by_path(session: Session, path: str):
    session.query(Video).filter_by(path=path).delete()
    session.commit()


def add_image(
    session: Session, path: str, modify_time: datetime.datetime, features: bytes
):
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
    video_list = (
        Video(
            path=path, modify_time=modify_time, frame_time=frame_time, features=features
        )
        for frame_time, features in frame_time_features_generator
    )
    session.bulk_save_objects(video_list)
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
    video = session.query(Video).filter_by(path=path).first()
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
    id_list, path_list, features_list = zip(*query)
    return id_list, path_list, features_list


def search_image_by_path(session: Session, path: str) -> list[tuple[int, str]]:
    """
    根据路径搜索图片，最多返回 MAX_RESULT_NUM 个数据
    :return: (图片id, 图片路径) 元组列表
    """
    return (
        session.query(Image.id, Image.path)
        .filter(Image.path.like("%" + path + "%"))
        .order_by(asc(Image.path))
        .limit(MAX_RESULT_NUM)
        .all()
    )


def search_video_by_path(session: Session, path: str):
    """
    根据路径搜索视频，最多返回 MAX_RESULT_NUM 个数据
    """
    return (
        session.query(Video.path)
        .distinct()
        .filter(Video.path.like("%" + path + "%"))
        .order_by(asc(Video.path))
        .limit(MAX_RESULT_NUM)
        .all()
    )
