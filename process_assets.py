# 预处理图片和视频，建立索引，加快搜索速度
import os
import numpy as np

from PIL import Image
from transformers import CLIPProcessor, CLIPModel, BertTokenizer, BertForSequenceClassification
import cv2
import torch

import logging
from config import *

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(pathname)s %(message)s "#配置输出日志格式
DATE_FORMAT = '%Y-%m-%d  %H:%M:%S %a ' #配置输出时间的格式，注意月份和天数不要搞乱了
logging.basicConfig(level=logging.DEBUG,
                    format=LOG_FORMAT,
                    datefmt = DATE_FORMAT ,
                    filename=r"log.txt" #有了filename参数就不会直接输出显示到控制台，而是直接写入文件
                    )

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif")  # 支持的图片拓展名
VIDEO_EXTENSIONS = (".mp4", ".flv", ".mov", ".mkv")  # 支持的视频拓展名
IGNORE_STRINGS = ("thumb", "avatar", "thumb", "icon", "cache")  # 如果路径或文件名包含这些字符串，就跳过（先把字符串转小写再对比）
FRAME_INTERVAL = 2  # 视频每隔多少秒取一帧，视频展示的时候，间隔小于等于2倍FRAME_INTERVAL的算为同一个素材，同时开始时间和结束时间各延长0.5个FRAME_INTERVAL

# global DEVICE
# DEVICE = "cuda"  # 推理设备，cpu/cuda/mps，建议先跑benchmark.py看看cpu还是显卡速度更快，因为数据搬运也需要时间
# 扫描的时候用cuda，搜索的时候改回cpu不然会报错无法进行搜索。

# @app.route('/api/setDevice', methods=['POST'])
def setDevice(device="cpu"):
    '''
    设置推理用的设备，目前扫描可以用cuda跟cpu，但是搜索的时候只能用cpu
    :Dec,str,default='cpu'，可选cpu跟cuda
    '''
    global DEVICE
    if DEVICE=="cpu":
        logging.info(f'Device:{DEVICE}')
    if device !=DEVICE:
        logging.info(f'Device从{DEVICE}改为{device}')
    DEVICE=device
    model = CLIPModel.from_pretrained(MODEL_NAME).to(torch.device(DEVICE))


logging.info("Loading model...")


model = CLIPModel.from_pretrained(MODEL_NAME).to(torch.device(DEVICE))
processor = CLIPProcessor.from_pretrained(MODEL_NAME)
text_tokenizer = BertTokenizer.from_pretrained(TEXT_MODEL_NAME)
# text_encoder = BertForSequenceClassification.from_pretrained(TEXT_MODEL_NAME).to(torch.device(DEVICE)).eval()
text_encoder = BertForSequenceClassification.from_pretrained(TEXT_MODEL_NAME).to(torch.device("cpu")).eval()#由于没把下面的调用改成cuda，所以这里指定用cpu进行文字推理
logging.info("Model loaded.")




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
    logging.info('扫描的扩展名是： {extensions}')
    # 遍历根目录及其子目录下的所有文件
    for path in paths:
        logging.info('开始扫描：%s'% path)
        for dir_path, dir_names, filenames in os.walk(path):
            if dir_path.startswith(skip_paths) or contain_strings(dir_path.lower(), IGNORE_STRINGS):
                logging.info("跳过目录/缩略图：%s"% dir_path)
                continue
            for filename in filenames:
                if contain_strings(filename.lower(), IGNORE_STRINGS):
                    continue
                # 判断文件是否为特定后缀结尾
                # logging.info(f'判断{filename}是否结尾包含{extensions}')
                if filename.lower().endswith(extensions):
                    # 获取图片文件的绝对路径
                    img_path = os.path.join(dir_path, filename)
                    # 将路径增加到文件集合
                    assets.add(img_path)
    return assets


def process_image(path):
    """
    处理图片并返回处理完成的数据
    :param path: string, 图片路径
    :return: <class 'numpy.nparray'>
    """
    try:
        image = Image.open(path)
        # 忽略小图片
        width, height = image.size
        if width < 64 or height < 64:
            return None
    except Exception as e:
        logging.warning(f"处理图片报错：{path}, {repr(e)}")
        return None
    try:
        inputs = processor(images=image, return_tensors="pt", padding=True).to(torch.device(DEVICE))
    except Exception as e:
        logging.warning(f"处理图片报错：{path}, {repr(e)}")
        return None
    feature = model.get_image_features(**inputs).cpu().detach().numpy()
    return feature


def process_video(path):
    """
    处理视频并返回处理完成的数据
    返回一个生成器，每调用一次则返回视频下一个帧的数据
    :param path: string, 视频路径
    :return: [int, <class 'numpy.nparray'>]
    """
    logging.info("处理视频中：%s"% path)
    try:
        video = cv2.VideoCapture(path)
        frame_rate = round(video.get(cv2.CAP_PROP_FPS))
        total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
        logging.info(f"fps:{frame_rate}, total: {total_frames}")
        current_frame = 0
        while True:
            if DEVICE == 'cpu' and current_frame % 100 == 0:
                print('CPU Doing')
                print(" \r进度：%d/%d  " % (current_frame, total_frames), end='')
            elif DEVICE == 'cuda' and current_frame % 400 == 0:
                print('Cuda Doing')
                print(" \r进度：%d/%d  " % (current_frame, total_frames), end='')
            ret, frame = video.read()
            if not ret:
                return
            if current_frame % (FRAME_INTERVAL * frame_rate) == 0:
                inputs = processor(images=frame, return_tensors="pt", padding=True).to(torch.device(DEVICE))
                feature = model.get_image_features(**inputs).cpu().detach().numpy()
                if feature is None:
                    logging.info("feature is None")
                    continue
                yield current_frame / frame_rate, feature
            current_frame += 1
    except Exception as e:
        logging.warning("处理视频出错：%s"% repr(e))
        return


def process_text(input_text):
    """
    预处理文字列表
    :param input_text: string
    :return: <class 'numpy.nparray'>
    """
    if not input_text:
        return None
    text = text_tokenizer(input_text, return_tensors='pt', padding=True)['input_ids']
    text_features = text_encoder(text).logits.cpu().detach().numpy()  # cpu推理
    return text_features


def match_text_and_image(text_feature, image_feature):
    """
    匹配文字和图片
    :param text_feature: <class 'numpy.nparray'>
    :param image_feature: <class 'numpy.nparray'>
    :return: <class 'numpy.nparray'>
    """
    new_image_feature = image_feature / np.linalg.norm(image_feature)
    new_text_feature = text_feature / np.linalg.norm(text_feature)
    score = (new_image_feature @ new_text_feature.T)
    return score


def match_batch(positive_feature, negative_feature, image_features, positive_threshold, negative_threshold):
    """
    匹配image_feature列表并返回分数
    :param positive_feature: <class 'numpy.ndarray'>
    :param negative_feature: <class 'numpy.ndarray'>
    :param image_features: [<class 'numpy.ndarray'>]
    :param positive_threshold: 正向提示分数阈值，高于此分数才显示
    :param negative_threshold: 反向提示分数阈值，低于此分数才显示
    :return: [float]
    """
    scores = []
    image_features = np.vstack(image_features)
    # 归一化
    if image_features.shape[0] == 1:
        new_features = image_features / np.linalg.norm(image_features)
    else:
        new_features = image_features / np.linalg.norm(image_features, axis=1, keepdims=True)
    # 计算匹配度
    new_text_positive_feature = positive_feature / np.linalg.norm(positive_feature)
    positive_scores = (new_features @ new_text_positive_feature.T)
    if negative_feature is not None:
        new_text_negative_feature = negative_feature / np.linalg.norm(negative_feature)
        negative_scores = (new_features @ new_text_negative_feature.T)
    # 根据阈值进行过滤
    for i in range(len(positive_scores)):
        if positive_scores[i] < positive_threshold / 100:
            scores.append(0)
            continue
        if negative_feature is not None:
            if negative_scores[i] > negative_threshold / 100:
                scores.append(0)
                continue
        scores.append(positive_scores[i])
    return scores
