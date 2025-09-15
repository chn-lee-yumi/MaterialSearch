# 预处理图片和视频，建立索引，加快搜索速度
import logging
import traceback

import cv2
import numpy as np
import requests
from PIL import Image
from tqdm import trange
from transformers import AutoModelForZeroShotImageClassification, AutoProcessor

from config import *

logger = logging.getLogger(__name__)

logger.info("Loading model...")
model = AutoModelForZeroShotImageClassification.from_pretrained(MODEL_NAME).to(DEVICE)
processor = AutoProcessor.from_pretrained(MODEL_NAME)
logger.info("Model loaded.")


def get_image_feature(images):
    """
    :param images: 图片列表
    :return: feature
    """
    if images is None or len(images) == 0:
        return None
    features = None
    try:
        inputs = processor(images=images, return_tensors="pt")["pixel_values"].to(DEVICE)
        features = model.get_image_features(inputs)
        normalized_features = features / torch.norm(features, dim=1, keepdim=True)  # 归一化，方便后续计算余弦相似度
        features = normalized_features.detach().cpu().numpy()
    except Exception as e:
        logger.exception("处理图片报错：type=%s error=%s" % (type(images), repr(e)))
        traceback.print_stack()
        if type(images) == list:
            print("images[0]:", images[0])
        else:
            print("images:", images)
        if features is not None:
            print("feature.shape:", features.shape)
            print("feature:", features)
        # 如果报错内容包含 not enough GPU video memory，就打印额外的日志
        if "not enough GPU video memory" in repr(e) and MODEL_NAME != "OFA-Sys/chinese-clip-vit-base-patch16":
            logger.error("显存不足，请使用小模型（OFA-Sys/chinese-clip-vit-base-patch16）！！！")
    return features


def get_image_data(path: str, ignore_small_images: bool = True):
    """
    获取图片像素数据，如果出错返回 None
    :param path: string, 图片路径
    :param ignore_small_images: bool, 是否忽略尺寸过小的图片
    :return: <class 'numpy.nparray'>, 图片数据，如果出错返回 None
    """
    try:
        image = Image.open(path)
        if ignore_small_images:
            width, height = image.size
            if width < IMAGE_MIN_WIDTH or height < IMAGE_MIN_HEIGHT:
                return None
                # processor 中也会这样预处理 Image
        # 在这里提前转为 np.array 避免到时候抛出异常
        image = image.convert('RGB')
        image = np.array(image)
        return image
    except Exception as e:
        logger.exception("打开图片报错：path=%s error=%s" % (path, repr(e)))
        traceback.print_stack()
        return None


def process_image(path, ignore_small_images=True):
    """
    处理图片，返回图片特征
    :param path: string, 图片路径
    :param ignore_small_images: bool, 是否忽略尺寸过小的图片
    :return: <class 'numpy.nparray'>, 图片特征
    """
    image = get_image_data(path, ignore_small_images)
    if image is None:
        return None
    feature = get_image_feature(image)
    return feature


def process_images(path_list, ignore_small_images=True):
    """
    处理图片，返回图片特征
    :param path_list: string, 图片路径列表
    :param ignore_small_images: bool, 是否忽略尺寸过小的图片
    :return: <class 'numpy.nparray'>, 图片特征
    """
    images = []
    for path in path_list.copy():
        image = get_image_data(path, ignore_small_images)
        if image is None:
            path_list.remove(path)
            continue
        images.append(image)
    if not images:
        return None, None
    feature = get_image_feature(images)
    return path_list, feature


def process_web_image(url):
    """
    处理网络图片，返回图片特征
    :param url: string, 图片URL
    :return: <class 'numpy.nparray'>, 图片特征
    """
    try:
        image = Image.open(requests.get(url, stream=True).raw)
    except Exception as e:
        logger.warning("获取图片报错：%s %s" % (url, repr(e)))
        return None
    feature = get_image_feature(image)
    return feature


def get_frames(video: cv2.VideoCapture):
    """ 
    获取视频的帧数据
    :return: (list[int], list[array]) (帧编号列表, 帧像素数据列表) 元组
    """
    frame_rate = round(video.get(cv2.CAP_PROP_FPS))
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.debug(f"fps: {frame_rate} total: {total_frames}")
    ids, frames = [], []
    for current_frame in trange(
            0, total_frames, FRAME_INTERVAL * frame_rate, desc="当前进度", unit="frame"
    ):
        # 在 FRAME_INTERVAL 为 2（默认值），frame_rate 为 24
        # 即 FRAME_INTERVAL * frame_rate == 48 时测试
        # 直接设置当前帧的运行效率低于使用 grab 跳帧
        # 如果需要跳的帧足够多，也许直接设置效率更高
        # video.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = video.read()
        if not ret:
            break
        ids.append(current_frame // frame_rate)
        frames.append(frame)
        if len(frames) == SCAN_PROCESS_BATCH_SIZE:
            yield ids, frames
            ids = []
            frames = []
        for _ in range(FRAME_INTERVAL * frame_rate - 1):
            video.grab()  # 跳帧
    yield ids, frames


def process_video(path):
    """
    处理视频并返回处理完成的数据
    返回一个生成器，每调用一次则返回视频下一个帧的数据
    :param path: string, 视频路径
    :return: [int, <class 'numpy.nparray'>], [当前是第几帧（被采集的才算），图片特征]
    """
    logger.info(f"处理视频中：{path}")
    video = None
    try:
        video = cv2.VideoCapture(path)
        for ids, frames in get_frames(video):
            if not frames:
                continue
            features = get_image_feature(frames)
            if features is None:
                logger.warning("features is None in process_video")
                continue
            for id, feature in zip(ids, features):
                yield id, feature
    except Exception as e:
        logger.exception("处理视频报错：path=%s error=%s" % (path, repr(e)))
        traceback.print_stack()
        if video is not None:
            frame_rate = round(video.get(cv2.CAP_PROP_FPS))
            total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
            print(f"fps: {frame_rate} total: {total_frames}")
            video.release()
        return


def process_text(input_text):
    """
    预处理文字，返回文字特征
    :param input_text: string, 被处理的字符串
    :return: <class 'numpy.nparray'>,  文字特征
    """
    feature = None
    if not input_text:
        return None
    try:
        text = processor(text=input_text, return_tensors="pt", padding=True)["input_ids"].to(DEVICE)
        feature = model.get_text_features(text)
        normalize_feature = feature / torch.norm(feature, dim=1, keepdim=True)  # 归一化，方便后续计算余弦相似度
        feature = normalize_feature.detach().cpu().numpy()
    except Exception as e:
        logger.exception("处理文字报错：text=%s error=%s" % (input_text, repr(e)))
        traceback.print_stack()
        if feature is not None:
            print("feature.shape:", feature.shape)
            print("feature:", feature)
    return feature


def match_text_and_image(text_feature, image_feature):
    """
    匹配文字和图片，返回余弦相似度
    :param text_feature: <class 'numpy.nparray'>, 文字特征
    :param image_feature: <class 'numpy.nparray'>, 图片特征
    :return: <class 'numpy.nparray'>, 文字和图片的余弦相似度，shape=(1, 1)
    """
    score = image_feature @ text_feature.T
    return score


def match_batch(
        positive_feature,
        negative_feature,
        image_features,
        positive_threshold,
        negative_threshold,
):
    """
    匹配image_feature列表并返回余弦相似度
    :param positive_feature: <class 'numpy.ndarray'>, 正向提示词特征，shape=(1, m)
    :param negative_feature: <class 'numpy.ndarray'>, 反向提示词特征，shape=(1, m)
    :param image_features: <class 'numpy.ndarray'>, 图片特征，shape=(n, m)
    :param positive_threshold: int/float, 正向提示分数阈值，高于此分数才显示
    :param negative_threshold: int/float, 反向提示分数阈值，低于此分数才显示
    :return: <class 'numpy.nparray'>, 提示词和每个图片余弦相似度列表，shape=(n, )，如果小于正向提示分数阈值或大于反向提示分数阈值则会置0
    """
    if positive_feature is None:  # 没有正向feature就把分数全部设成1
        positive_scores = np.ones(len(image_features))
    else:
        positive_scores = image_features @ positive_feature.T
    if negative_feature is not None:
        negative_scores = image_features @ negative_feature.T
    # 根据阈值进行过滤
    scores = np.where(positive_scores < positive_threshold / 100, 0, positive_scores)
    if negative_feature is not None:
        scores = np.where(negative_scores > negative_threshold / 100, 0, scores)
    return scores.squeeze(-1)
