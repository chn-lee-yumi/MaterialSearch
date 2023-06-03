import hashlib
import logging

import numpy as np

from config import LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def get_file_hash(path):
    """
    计算文件hash
    :param path: string, 文件路径
    :return: string, 十六进制字符串
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
