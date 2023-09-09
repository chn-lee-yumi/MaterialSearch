import base64
import logging
import time
from functools import lru_cache

import numpy as np
from flask import abort
from sqlalchemy import asc

import crud
from config import *
from database import Image, Video, db
from process_assets import match_batch, process_image, process_text

logger = logging.getLogger(__name__)


def clean_cache():
    """
    清空搜索缓存
    :return: None
    """
    search_image_by_text.cache_clear()
    search_image_by_image.cache_clear()
    search_video_by_text.cache_clear()
    search_video_by_image.cache_clear()
    search_file.cache_clear()


def search_image_by_feature(
    positive_feature,
    negative_feature=None,
    positive_threshold=POSITIVE_THRESHOLD,
    negative_threshold=NEGATIVE_THRESHOLD,
):
    """
    通过特征搜索图片
    :param positive_feature: np.array, 正向特征向量
    :param negative_feature: np.array, 反向特征向量
    :param positive_threshold: int/float, 正向阈值
    :param negative_threshold: int/float, 反向阈值
    :return: list[dict], 搜索结果列表
    """
    scores_list = []
    t0 = time.time()
    ids, paths, features = crud.get_image_id_path_features(db.session)
    features = np.frombuffer(b''.join(features), dtype=np.float32).reshape(len(features), -1)
    if len(ids) == 0:  # 没有素材，直接返回空
        return []
    scores = match_batch(
        positive_feature,
        negative_feature,
        features,
        positive_threshold,
        negative_threshold,
    )
    for i in range(len(ids)):
        if not scores[i]:
            continue
        scores_list.append(
            {
                "url": "api/get_image/%d" % ids[i],
                "path": paths[i],
                "score": float(scores[i]),
            }
        )
    logger.info("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


@lru_cache(maxsize=CACHE_SIZE)
def search_image_by_text(
    positive_prompt="",
    negative_prompt="",
    positive_threshold=POSITIVE_THRESHOLD,
    negative_threshold=NEGATIVE_THRESHOLD,
):
    """
    使用文字搜图片
    :param positive_prompt: string, 正向提示词
    :param negative_prompt: string, 反向提示词
    :param positive_threshold: int/float, 正向阈值
    :param negative_threshold: int/float, 反向阈值
    :return: list[dict], 搜索结果列表
    """
    positive_feature = process_text(positive_prompt)
    negative_feature = process_text(negative_prompt)
    return search_image_by_feature(
        positive_feature, negative_feature, positive_threshold, negative_threshold
    )


@lru_cache(maxsize=CACHE_SIZE)
def search_image_by_image(img_id_or_path, threshold=IMAGE_THRESHOLD):
    """
    使用图片搜图片
    :param img_id_or_path: int/string, 图片ID 或 图片路径
    :param threshold: int/float, 搜索阈值
    :return: list[dict], 搜索结果列表
    """
    try:
        img_id = int(img_id_or_path)
    except ValueError as e:
        img_path = img_id_or_path
    if img_id:
        image = db.session.query(Image).filter_by(id=img_id).first()
        if not image:
            logger.warning("用数据库的图来进行搜索，但id在数据库中不存在")
            return []
        feature = np.frombuffer(image.features, dtype=np.float32).reshape(1, -1)
    elif img_path:
        feature = process_image(img_path)
    return search_image_by_feature(feature, None, threshold)


def get_index_pairs(scores):
    """
    根据每一帧的余弦相似度计算素材片段
    :param scores: [<class 'numpy.nparray'>], 余弦相似度列表，里面每个元素的shape=(1, 1)
    :return: 返回连续的帧序号列表，如第2-5帧、第11-13帧都符合搜索内容，则返回[(2,5),(11,13)]
    """
    indexes = []
    for i in range(len(scores)):
        if scores[i]:
            indexes.append(i)
    result = []
    start_index = -1
    for i in range(len(indexes)):
        if start_index == -1:
            start_index = indexes[i]
        elif indexes[i] - indexes[i - 1] > 2:  # 允许中间空1帧
            result.append((start_index, indexes[i - 1]))
            start_index = indexes[i]
    if start_index != -1:
        result.append((start_index, indexes[-1]))
    return result


def search_video_by_feature(
    positive_feature,
    negative_feature=None,
    positive_threshold=POSITIVE_THRESHOLD,
    negative_threshold=NEGATIVE_THRESHOLD,
):
    """
    通过特征搜索视频
    :param positive_feature: np.array, 正向特征向量
    :param negative_feature: np.array, 反向特征向量
    :param positive_threshold: int/float, 正向阈值
    :param negative_threshold: int/float, 反向阈值
    :return: list[dict], 搜索结果列表
    """
    t0 = time.time()
    scores_list = []
    for path in db.session.query(Video.path).distinct():  # 逐个视频比对
        path = path[0]
        frames = (
            db.session.query(Video)
            .filter_by(path=path)
            .order_by(Video.frame_time)
            .all()
        )
        image_features = list(
            map(
                lambda x: np.frombuffer(x.features, dtype=np.float32).reshape(
                    1, -1
                ),
                frames,
            )
        )
        scores = match_batch(
            positive_feature,
            negative_feature,
            image_features,
            positive_threshold,
            negative_threshold,
        )
        index_pairs = get_index_pairs(scores)
        for start_index, end_index in index_pairs:
            # 间隔小于等于2倍FRAME_INTERVAL的算为同一个素材，同时开始时间和结束时间各延长0.5个FRAME_INTERVAL
            score = max(scores[start_index : end_index + 1])
            if start_index > 0:
                start_time = int(
                    (
                        frames[start_index].frame_time
                        + frames[start_index - 1].frame_time
                    )
                    / 2
                )
            else:
                start_time = frames[start_index].frame_time
            if end_index < len(scores) - 1:
                end_time = int(
                    (
                        frames[end_index].frame_time
                        + frames[end_index + 1].frame_time
                    )
                    / 2
                    + 0.5
                )
            else:
                end_time = frames[end_index].frame_time
            scores_list.append(
                {
                    "url": "api/get_video/%s"
                    % base64.urlsafe_b64encode(path.encode()).decode()
                    + "#t=%.1f,%.1f" % (start_time, end_time),
                    "path": path,
                    "score": score,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )
    logger.info("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


@lru_cache(maxsize=CACHE_SIZE)
def search_video_by_text(
    positive_prompt="",
    negative_prompt="",
    positive_threshold=POSITIVE_THRESHOLD,
    negative_threshold=NEGATIVE_THRESHOLD,
):
    """
    使用文字搜视频
    :param positive_prompt: string, 正向提示词
    :param negative_prompt: string, 反向提示词
    :param positive_threshold: int/float, 正向阈值
    :param negative_threshold: int/float, 反向阈值
    :return: list[dict], 搜索结果列表
    """
    positive_feature = process_text(positive_prompt)
    negative_feature = process_text(negative_prompt)
    return search_video_by_feature(
        positive_feature, negative_feature, positive_threshold, negative_threshold
    )


@lru_cache(maxsize=CACHE_SIZE)
def search_video_by_image(img_id_or_path, threshold=IMAGE_THRESHOLD):
    """
    使用图片搜视频
    :param img_id_or_path: int/string, 图片ID 或 图片路径
    :param threshold: int/float, 搜索阈值
    :return: list[dict], 搜索结果列表
    """
    try:
        img_id = int(img_id_or_path)
    except ValueError as e:
        img_path = img_id_or_path
    if img_id:
        image = db.session.query(Image).filter_by(id=img_id).first()
        if not image:
            logger.warning("用数据库的图来进行搜索，但id在数据库中不存在")
            return []
        feature = np.frombuffer(image.features, dtype=np.float32).reshape(1, -1)
    elif img_path:
        feature = process_image(img_path)
    return search_video_by_feature(feature, None, threshold)


@lru_cache(maxsize=CACHE_SIZE)
def search_file(path, file_type):
    """
    通过路径搜索图片或视频
    :param path: 路径
    :param file_type: 文件类型，"image"或"video"
    :return:
    """
    if file_type == "image":
        files = (
            db.session.query(Image)
            .filter(Image.path.like("%" + path + "%"))
            .order_by(asc(Image.path))
        )
    elif file_type == "video":
        files = (
            db.session.query(Video.path)
            .distinct()
            .filter(Video.path.like("%" + path + "%"))
            .order_by(asc(Video.path))
        )
    else:
        abort(400)
    file_list = []
    for file in files:
        if file_type == "image":
            file_list.append({"url": "api/get_image/%d" % file.id, "path": file.path})
        elif file_type == "video":
            file_list.append(
                {
                    "url": "api/get_video/%s"
                    % base64.urlsafe_b64encode(file.path.encode()).decode(),
                    "path": file.path,
                }
            )
    return file_list
