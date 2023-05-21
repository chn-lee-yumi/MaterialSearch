import hashlib
import logging

import numpy as np

from config import *

logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def get_file_hash(path):
    """
    计算文件hash
    :param path: 文件路径
    :return: 十六进制字符串
    """
    _hash = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while True:
                data = f.read(1048576)
                if not data:
                    break
                _hash.update(data)
    except Exception as e:
        logger.error(f"计算hash出错：{path} {repr(e)}")
        return None
    return _hash.hexdigest()


def get_string_hash(string):
    """
    计算字符串hash
    :param string: 字符串
    :return: 十六进制字符串
    """
    _hash = hashlib.sha1()
    _hash.update(string.encode("utf8"))
    return _hash.hexdigest()


def softmax(scores):
    exp_scores = np.exp(scores)
    return exp_scores / np.sum(exp_scores)
