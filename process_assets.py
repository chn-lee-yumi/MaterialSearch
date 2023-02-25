# 预处理图片和视频，建立索引，加快搜索速度
import os
import pickle
import time

from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import cv2
import torch

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif")  # 支持的图片拓展名
VIDEO_EXTENSIONS = (".mp4", ".flv", ".mov")  # 支持的视频拓展名
IGNORE_STRINGS = ("thumb", "avatar", "thumb", "icon", "cache")  # 如果路径或文件名包含这些字符串，就跳过（先把字符串转小写再对比）
FRAME_INTERVAL = 10  # 视频每隔多少秒取一帧
MAX_FRAMES = 50  # 一个视频最多提取多少帧
POSITIVE_THRESHOLD = 27  # 正向搜索词搜出来的素材，高于这个分数才展示
NEGATIVE_THRESHOLD = 27  # 反向搜索词搜出来的素材，低于这个分数才展示
# DEVICE = "cpu"  # 推理设备，mps或cpu
# cpu: 18s
# mps: 40s

print("Loading model...")
# 支持的模型：clip-vit-base-patch16 clip-vit-base-patch32 clip-vit-large-patch14 clip-vit-large-patch14-336
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch16")
# model = CLIPModel.from_pretrained("openai/clip-vit-base-patch16").to(torch.device(DEVICE))
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch16")
print("Model loaded.")


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
                # print("跳过目录/缩略图：", dir_path)
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


def process_image(path):
    """
    处理图片并返回处理完成的数据
    :param path: string, 图片路径
    :return: <class 'torch.Tensor'>
    """
    try:
        image = Image.open(path)
        # 忽略小图片
        width, height = image.size
        if width < 64 or height < 64:
            return None
    except Exception as e:
        print("处理图片报错：", path, repr(e))
        return None
    try:
        # inputs = processor(images=image, return_tensors="pt", padding=True).to(torch.device(DEVICE))
        inputs = processor(images=image, return_tensors="pt", padding=True)
    except Exception as e:
        print("处理图片报错：", path, repr(e))
        return None
    feature = model.get_image_features(**inputs)
    # return feature.to(torch.device("cpu"))
    return feature


def process_video(path):
    """
    处理视频并返回处理完成的数据
    :param path: string, 图片路径
    :return: [<class 'torch.Tensor'>]
    """
    print("处理视频中：", path)
    video = cv2.VideoCapture(path)
    frame_rate = video.get(cv2.CAP_PROP_FPS)
    total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
    try:
        if total_frames / (frame_rate * FRAME_INTERVAL) > MAX_FRAMES:  # 超过最大帧数
            frame_mod = int(total_frames / MAX_FRAMES)
        else:  # 每FRAME_INTERVAL秒截一个图
            frame_mod = frame_rate * FRAME_INTERVAL
        current_frame = 0
        feature_list = []
        while True:
            ret, frame = video.read()
            if not ret:
                break
            if current_frame % frame_mod == 0:
                # inputs = processor(images=frame, return_tensors="pt", padding=True).to(torch.device(DEVICE))
                inputs = processor(images=frame, return_tensors="pt", padding=True)
                feature = model.get_image_features(**inputs)
                # feature_list.append(feature.to(torch.device("cpu")))
                feature_list.append(pickle.loads(pickle.dumps(feature)))  # 先dump再load可以减少内存使用，不然一帧占用一百多M内存
            current_frame += 1
    except Exception as e:
        print("处理视频出错：", repr(e))
        return None
    return feature_list


def process_text(input_text):
    """
    预处理文字列表
    :param input_text: string
    :return: <class 'torch.Tensor'>
    """
    # inputs = processor(text=input_text, return_tensors="pt", padding=True).to(torch.device(DEVICE))
    inputs = processor(text=input_text, return_tensors="pt", padding=True)
    return model.get_text_features(**inputs)


def match_image(positive_feature, negative_feature, image_feature):
    """
    匹配文字和图片
    :param positive_feature: <class 'torch.Tensor'>
    :param negative_feature: <class 'torch.Tensor'>
    :param image_feature: <class 'torch.Tensor'>
    :return: <class 'torch.Tensor'>
    """
    new_image_feature = image_feature / image_feature.norm(dim=-1, keepdim=True)
    new_text_positive_feature = positive_feature / positive_feature.norm(dim=-1, keepdim=True)
    positive_score = (new_image_feature @ new_text_positive_feature.T) * 100
    if positive_score < POSITIVE_THRESHOLD:
        return None
    if negative_feature is not None:
        new_text_negative_feature = negative_feature / negative_feature.norm(dim=-1, keepdim=True)
        negative_score = (new_image_feature @ new_text_negative_feature.T) * 100
        if negative_score > NEGATIVE_THRESHOLD:
            return None
    return positive_score


def match_video(positive_feature, negative_feature, image_feature):
    """
    匹配文字和视频
    :param positive_feature: <class 'torch.Tensor'>
    :param negative_feature: <class 'torch.Tensor'>
    :param image_feature: [<class 'torch.Tensor'>]
    :return: <class 'torch.Tensor'>
    """
    new_text_positive_feature = positive_feature / positive_feature.norm(dim=-1, keepdim=True)
    if negative_feature is not None:
        new_text_negative_feature = negative_feature / negative_feature.norm(dim=-1, keepdim=True)
    scores = set()

    features = torch.stack(image_feature)
    new_features = features / features.norm(dim=-1, keepdim=True)
    positive_scores = (new_features @ new_text_positive_feature.T) * 100
    if negative_feature is not None:
        negative_scores = (new_features @ new_text_negative_feature.T) * 100
    for i in range(len(positive_scores)):
        if positive_scores[i] < POSITIVE_THRESHOLD:
            continue
        if negative_feature is not None:
            if negative_scores[i] > NEGATIVE_THRESHOLD:
                continue
        scores.add(positive_scores[i])

    # for feature in image_feature:
    #     new_image_feature = feature / feature.norm(dim=-1, keepdim=True)
    #     positive_score = (new_image_feature @ new_text_positive_feature.T) * 100
    #     if positive_score < POSITIVE_THRESHOLD:
    #         continue
    #     if negative_feature is not None:
    #         negative_score = (new_image_feature @ new_text_negative_feature.T) * 100
    #         if negative_score > NEGATIVE_THRESHOLD:
    #             continue
    #     scores.add(positive_score)

    if scores:
        return max(scores)
    return None
