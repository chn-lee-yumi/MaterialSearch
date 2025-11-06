"""
图片属性计算工具
用于计算图片的宽高比、标准比例、文件格式、感知哈希等
"""

import os
import logging
import imagehash
from PIL import Image
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def get_standard_aspect_ratio(ratio: float) -> str:
    """
    获取标准宽高比

    Args:
        ratio: 实际宽高比

    Returns:
        str: 标准宽高比字符串
    """
    standard_ratios = {
        1.0: "1:1",
        1.333: "4:3",
        1.5: "3:2",
        1.6: "16:10",
        1.778: "16:9",
        2.0: "2:1",
        2.333: "21:9",
        0.75: "3:4",
        0.667: "2:3",
        0.5625: "9:16",
    }

    # 找到最接近的标准比例
    min_diff = float('inf')
    result = f"{ratio:.2f}:1"

    for standard_ratio, label in standard_ratios.items():
        diff = abs(ratio - standard_ratio)
        if diff < min_diff:
            min_diff = diff
            result = label

    # 如果差异小于 0.05，认为是标准比例
    if min_diff > 0.05:
        result = f"{ratio:.2f}:1"

    return result


def calculate_image_properties(image_path: str) -> Optional[Dict]:
    """
    计算图片的扩展属性

    Args:
        image_path: 图片路径

    Returns:
        Dict: 图片属性字典，包含：
            - width: 宽度
            - height: 高度
            - aspect_ratio: 宽高比
            - aspect_ratio_standard: 标准宽高比
            - file_size: 文件大小
            - file_format: 文件格式
            - phash: 感知哈希（可选）

        如果失败返回 None
    """
    try:
        if not os.path.exists(image_path):
            return None

        with Image.open(image_path) as img:
            width, height = img.size

            # 跳过太小的图片
            if width < 10 or height < 10:
                return None

            aspect_ratio = round(width / height, 3)
            aspect_ratio_standard = get_standard_aspect_ratio(aspect_ratio)
            file_size = os.path.getsize(image_path)
            file_format = img.format.lower() if img.format else os.path.splitext(image_path)[1][1:].lower()

            # 计算感知哈希（用于去重）
            try:
                phash = str(imagehash.phash(img))
            except Exception as e:
                logger.warning(f"计算感知哈希失败 {image_path}: {e}")
                phash = None

            return {
                'width': width,
                'height': height,
                'aspect_ratio': aspect_ratio,
                'aspect_ratio_standard': aspect_ratio_standard,
                'file_size': file_size,
                'file_format': file_format,
                'phash': phash,
            }

    except Exception as e:
        logger.error(f"计算图片属性失败 {image_path}: {e}")
        return None


def calculate_video_properties(video_path: str) -> Optional[Dict]:
    """
    计算视频的扩展属性

    Args:
        video_path: 视频路径

    Returns:
        Dict: 视频属性字典，包含：
            - width: 宽度
            - height: 高度
            - aspect_ratio: 宽高比
            - duration: 时长（秒）
            - file_size: 文件大小
            - file_format: 文件格式

        如果失败返回 None
    """
    try:
        import cv2

        if not os.path.exists(video_path):
            return None

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        cap.release()

        duration = int(frame_count / fps) if fps > 0 else 0
        aspect_ratio = round(width / height, 3) if height > 0 else 0
        file_size = os.path.getsize(video_path)
        file_format = os.path.splitext(video_path)[1][1:].lower()

        return {
            'width': width,
            'height': height,
            'aspect_ratio': aspect_ratio,
            'duration': duration,
            'file_size': file_size,
            'file_format': file_format,
        }

    except ImportError:
        logger.warning("cv2 模块未安装，无法计算视频属性")
        return None
    except Exception as e:
        logger.error(f"计算视频属性失败 {video_path}: {e}")
        return None
