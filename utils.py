import hashlib
import logging
import platform
import subprocess

import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener

from config import LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
register_heif_opener()


def get_hash(bytesio):
    """
    计算字节流的 hash
    :param bytesio: bytes 或 BytesIO
    :return: string, 十六进制字符串
    """
    _hash = hashlib.sha1()
    if type(bytesio) is bytes:
        _hash.update(bytesio)
        return _hash.hexdigest()
    try:
        while True:
            data = bytesio.read(1048576)
            if not data:
                break
            _hash.update(data)
    except Exception as e:
        logger.error(f"计算hash出错：{bytesio} {repr(e)}")
        return None
    bytesio.seek(0)  # 归零，用于后续写入文件
    return _hash.hexdigest()


def get_string_hash(string):
    """
    计算字符串hash
    :param string: string, 字符串
    :return: string, 十六进制字符串
    """
    _hash = hashlib.sha1()
    _hash.update(string.encode("utf8"))
    return _hash.hexdigest()


def softmax(x):
    """
    计算softmax，使得每一个元素的范围都在(0,1)之间，并且所有元素的和为1。
    softmax其实还有个temperature参数，目前暂时不用。
    :param x: [float]
    :return: [float]
    """
    exp_scores = np.exp(x)
    return exp_scores / np.sum(exp_scores)


def format_seconds(seconds):
    """
    将秒数转成时分秒格式
    :param seconds: int, 秒数
    :return: "时:分:秒"
    """
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def crop_video(input_file, output_file, start_time, end_time):
    """
    调用ffmpeg截取视频片段
    :param input_file: 要截取的文件路径
    :param output_file: 保存文件路径
    :param start_time: int, 开始时间，单位为秒
    :param end_time: int, 结束时间，单位为秒
    :return: None
    """
    cmd = 'ffmpeg'
    if platform.system() == 'Windows':
        cmd += ".exe"
    command = [
        cmd,
        '-ss', format_seconds(start_time),
        '-to', format_seconds(end_time),
        '-i', input_file,
        '-c:v', 'copy',
        '-c:a', 'copy',
        output_file
    ]
    logger.info("Crop video:", " ".join(command))
    subprocess.run(command)


def resize_image_with_aspect_ratio(image_path, target_size, convert_rgb=False):
    image = Image.open(image_path)
    if convert_rgb and image.mode in ("RGBA", "P"):
        image = image.convert('RGB')
    # 计算调整后图像的目标大小及长宽比
    width, height = image.size
    aspect_ratio = width / height
    target_width, target_height = target_size
    target_aspect_ratio = target_width / target_height
    # 计算调整后图像的实际大小
    if target_aspect_ratio < aspect_ratio:
        # 以目标宽度为准进行调整
        new_width = target_width
        new_height = int(target_width / aspect_ratio)
    else:
        # 以目标高度为准进行调整
        new_width = int(target_height * aspect_ratio)
        new_height = target_height
    # 调整图像的大小
    resized_image = image.resize((new_width, new_height))
    return resized_image
