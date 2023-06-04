# 预处理图片和视频，建立索引，加快搜索速度
import concurrent.futures
import logging
import os

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel, BertTokenizer, BertForSequenceClassification

from config import *

logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

logger.info("Loading model...")
model = CLIPModel.from_pretrained(MODEL_NAME).to(torch.device(DEVICE))
processor = CLIPProcessor.from_pretrained(MODEL_NAME)
if LANGUAGE == "Chinese":
    text_tokenizer = BertTokenizer.from_pretrained(TEXT_MODEL_NAME)
    text_encoder = BertForSequenceClassification.from_pretrained(TEXT_MODEL_NAME).eval().to(torch.device(DEVICE_TEXT))
logger.info("Model loaded.")


def contain_strings(text, sub_set):
    """
    判断字符串里是否包含某些子字符串
    :param text: 被判断的字符串
    :param sub_set: 子字符串集合
    :return: Bool
    """
    for sub in sub_set:
        if sub in text:
            return True
    return False


def create_dir_if_not_exists(dir_path):
    """
    判断目录是否存在，如果目录不存在，则创建目录
    :param dir_path: string, 目录路径
    :return: None
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def scan_dir(paths, skip_paths, extensions):
    """
    遍历文件并返回特定后缀结尾的文件集合
    :param paths: (string), 根目录
    :param skip_paths: (string), 忽略目录
    :param extensions: tuple, 文件后缀名列表
    :return: set, 文件路径集合
    """
    assets = set()
    # 遍历根目录及其子目录下的所有文件
    for path in paths:
        for dir_path, dir_names, filenames in os.walk(path):
            if dir_path.startswith(skip_paths) or contain_strings(dir_path.lower(), IGNORE_STRINGS):
                logger.debug(f"跳过目录/缩略图：{dir_path}")
                continue
            for filename in filenames:
                if contain_strings(filename.lower(), IGNORE_STRINGS):
                    continue
                # 判断文件是否为特定后缀结尾
                if filename.lower().endswith(extensions):
                    # 获取图片文件的绝对路径
                    img_path = os.path.join(dir_path, filename)
                    # 将路径增加到文件集合
                    assets.add(img_path)
    return assets


def process_image(path, ignore_small_images=True):
    """
    处理图片，返回图片特征
    :param path: string, 图片路径
    :param ignore_small_images: bool, 是否忽略尺寸过小的图片
    :return: <class 'numpy.nparray'>, 图片特征
    """
    try:
        image = Image.open(path)
        # 忽略小图片
        if ignore_small_images:
            width, height = image.size
            if width < IMAGE_MIN_WIDTH or height < IMAGE_MIN_HEIGHT:
                return None
    except Exception as e:
        logger.warning(f"处理图片报错：{path} {repr(e)}")
        return None
    try:
        inputs = processor(images=image, return_tensors="pt", padding=True)['pixel_values'].to(torch.device(DEVICE))
    except Exception as e:
        logger.warning(f"处理图片报错：{path} {repr(e)}")
        return None
    feature = model.get_image_features(inputs).detach().cpu().numpy()
    return feature


def process_video(path):
    """
    处理视频并返回处理完成的数据
    返回一个生成器，每调用一次则返回视频下一个帧的数据
    :param path: string, 视频路径
    :return: [int, <class 'numpy.nparray'>], [当前是第几帧（被采集的才算），图片特征]
    """
    logger.info(f"处理视频中：{path}")
    try:
        video = cv2.VideoCapture(path)
        frame_rate = round(video.get(cv2.CAP_PROP_FPS))
        total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
        logger.debug(f"fps: {frame_rate} total: {total_frames}")
        current_frame = 0
        while True:
            print("\r进度：%d/%d  " % (current_frame, total_frames), end='')
            ret, frame = video.read()
            if not ret:
                return
            if current_frame % (FRAME_INTERVAL * frame_rate) == 0:
                inputs = processor(images=frame, return_tensors="pt", padding=True)['pixel_values'].to(torch.device(DEVICE))
                feature = model.get_image_features(inputs).detach().cpu().numpy()
                if feature is None:
                    logger.warning("feature is None")
                    continue
                yield current_frame / frame_rate, feature
            current_frame += 1
    except Exception as e:
        logger.warning(f"处理视频出错：{path} {repr(e)}")
        return


def process_text(input_text):
    """
    预处理文字，返回文字特征
    :param input_text: string, 被处理的字符串
    :return: <class 'numpy.nparray'>,  文字特征
    """
    if not input_text:
        return None
    if LANGUAGE == "Chinese":
        text = text_tokenizer(input_text, return_tensors='pt', padding=True)['input_ids'].to(torch.device(DEVICE_TEXT))
        text_features = text_encoder(text).logits.detach().cpu().numpy()
    else:
        text = processor(text=input_text, return_tensors="pt", padding=True)['input_ids'].to(torch.device(DEVICE))
        text_features = model.get_text_features(text).detach().cpu().numpy()
    return text_features


def match_text_and_image(text_feature, image_feature):
    """
    匹配文字和图片，返回余弦相似度
    :param text_feature: <class 'numpy.nparray'>, 文字特征
    :param image_feature: <class 'numpy.nparray'>, 图片特征
    :return: <class 'numpy.nparray'>, 文字和图片的余弦相似度，shape=(1, 1)
    """
    score = (image_feature @ text_feature.T) / (np.linalg.norm(image_feature) * np.linalg.norm(text_feature))
    # 上面的计算等价于下面三步：
    # new_image_feature = image_feature / np.linalg.norm(image_feature)
    # new_text_feature = text_feature / np.linalg.norm(text_feature)
    # score = (new_image_feature @ new_text_feature.T)
    return score


def normalize_features(features):
    """
    归一化
    :param features: [<class 'numpy.nparray'>], 特征
    :return: <class 'numpy.nparray'>, 归一化后的特征
    """
    return features / np.linalg.norm(features, axis=1, keepdims=True)


def multithread_normalize(features):
    """
    多线程执行归一化，只有对大矩阵效果才好
    :param features:  [<class 'numpy.nparray'>], 特征
    :return: <class 'numpy.nparray'>, 归一化后的特征
    """
    num_threads = os.cpu_count()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        # 将图像特征分成等分，每个线程处理一部分
        chunk_size = len(features) // num_threads
        chunks = [features[i:i + chunk_size] for i in range(0, len(features), chunk_size)]
        # 并发执行特征归一化
        normalized_chunks = executor.map(normalize_features, chunks)
    # 将处理后的特征重新合并
    return np.concatenate(list(normalized_chunks))


def match_batch(positive_feature, negative_feature, image_features, positive_threshold, negative_threshold):
    """
    匹配image_feature列表并返回余弦相似度
    :param positive_feature: <class 'numpy.ndarray'>, 正向提示词特征
    :param negative_feature: <class 'numpy.ndarray'>, 反向提示词特征
    :param image_features: [<class 'numpy.ndarray'>], 图片特征列表
    :param positive_threshold: int/float, 正向提示分数阈值，高于此分数才显示
    :param negative_threshold: int/float, 反向提示分数阈值，低于此分数才显示
    :return: [<class 'numpy.nparray'>], 提示词和每个图片余弦相似度列表，里面每个元素的shape=(1, 1)，如果小于正向提示分数阈值或大于反向提示分数阈值则会置0
    """
    image_features = np.concatenate(image_features, axis=0)
    # 计算余弦相似度
    if len(image_features) > 1024:  # 多线程只对大矩阵效果好，1024是随便写的
        new_features = multithread_normalize(image_features)
    else:
        new_features = normalize_features(image_features)
    new_text_positive_feature = positive_feature / np.linalg.norm(positive_feature)
    positive_scores = (new_features @ new_text_positive_feature.T)
    if negative_feature is not None:
        new_text_negative_feature = negative_feature / np.linalg.norm(negative_feature)
        negative_scores = (new_features @ new_text_negative_feature.T)
    # 根据阈值进行过滤
    scores = np.where(positive_scores < positive_threshold / 100, 0, positive_scores)
    if negative_feature is not None:
        scores = np.where(negative_scores > negative_threshold / 100, 0, scores)
    return scores
