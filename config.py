import importlib.util
import os

import torch

from env import *

pre_env()
env()  # 函数定义在加密代码中，请忽略 Unresolved reference 'env'
post_env()

# *****服务器配置*****
HOST = os.getenv('HOST', '127.0.0.1')  # 监听IP，如果想允许远程访问，把这个改成0.0.0.0
PORT = int(os.getenv('PORT', 8085))  # 监听端口

# *****扫描配置*****
# Windows系统的路径写法例子：'D:/照片'
ASSETS_PATH = tuple(os.getenv('ASSETS_PATH', '/home,/srv').split(','))  # 素材所在的目录，绝对路径，逗号分隔
SKIP_PATH = tuple(os.getenv('SKIP_PATH', '/tmp').split(','))  # 跳过扫描的目录，绝对路径，逗号分隔
IMAGE_EXTENSIONS = tuple(os.getenv('IMAGE_EXTENSIONS', '.jpg,.jpeg,.png,.gif,.heic,.webp,.bmp').split(','))  # 支持的图片拓展名，逗号分隔，请填小写
VIDEO_EXTENSIONS = tuple(os.getenv('VIDEO_EXTENSIONS', '.mp4,.flv,.mov,.mkv,.webm,.avi').split(','))  # 支持的视频拓展名，逗号分隔，请填小写
IGNORE_STRINGS = tuple(os.getenv('IGNORE_STRINGS', 'thumb,avatar,__MACOSX,icons,cache').lower().split(','))  # 如果路径或文件名包含这些字符串，就跳过，逗号分隔，不区分大小写
FRAME_INTERVAL = max(int(os.getenv('FRAME_INTERVAL', 2)), 1)  # 视频每隔多少秒取一帧，视频展示的时候，间隔小于等于2倍FRAME_INTERVAL的算为同一个素材，同时开始时间和结束时间各延长0.5个FRAME_INTERVAL，要求为整数，最小为1
SCAN_PROCESS_BATCH_SIZE = int(os.getenv('SCAN_PROCESS_BATCH_SIZE', 4))  # 等读取的帧数到这个数量后再一次性输入到模型中进行批量计算，从而提高效率。显存较大可以调高这个值。
IMAGE_MIN_WIDTH = int(os.getenv('IMAGE_MIN_WIDTH', 64))  # 图片最小宽度，小于此宽度则忽略。不需要可以改成0。
IMAGE_MIN_HEIGHT = int(os.getenv('IMAGE_MIN_HEIGHT', 64))  # 图片最小高度，小于此高度则忽略。不需要可以改成0。
AUTO_SCAN = os.getenv('AUTO_SCAN', 'False').lower() == 'true'  # 是否自动扫描，如果开启，则会在指定时间内进行扫描，每天只会扫描一次
AUTO_SCAN_START_TIME = tuple(map(int, os.getenv('AUTO_SCAN_START_TIME', '22:30').split(':')))  # 自动扫描开始时间
AUTO_SCAN_END_TIME = tuple(map(int, os.getenv('AUTO_SCAN_END_TIME', '8:00').split(':')))  # 自动扫描结束时间
AUTO_SAVE_INTERVAL = int(os.getenv('AUTO_SAVE_INTERVAL', 100))  # 扫描自动保存间隔，默认为每 100 个文件自动保存一次

# *****模型配置*****
# 更换模型需要删库重新扫描！否则搜索会报错。数据库路径见下面SQLALCHEMY_DATABASE_URL参数。模型越大，扫描速度越慢，且占用的内存和显存越大。
# 如果显存较小且用了较大的模型，并在扫描的时候出现了"CUDA out of memory"，请换成较小的模型。如果显存充足，可以调大上面的SCAN_PROCESS_BATCH_SIZE来提高扫描速度。
# 4G显存推荐参数：小模型，SCAN_PROCESS_BATCH_SIZE=6
# 8G显存推荐参数：小模型，SCAN_PROCESS_BATCH_SIZE=12
# 不同模型不同显存大小请自行摸索搭配。
# 中文小模型： "OFA-Sys/chinese-clip-vit-base-patch16"
# 中文大模型："OFA-Sys/chinese-clip-vit-large-patch14-336px"
# 中文超大模型："OFA-Sys/chinese-clip-vit-huge-patch14"
# 英文小模型： "openai/clip-vit-base-patch16"
# 英文大模型："openai/clip-vit-large-patch14-336"
MODEL_NAME = os.getenv('MODEL_NAME', "OFA-Sys/chinese-clip-vit-base-patch16")  # CLIP模型
DEVICE = os.getenv('DEVICE', 'auto')  # 推理设备，auto/cpu/cuda/mps

# *****搜索配置*****
CACHE_SIZE = int(os.getenv('CACHE_SIZE', 64))  # 搜索缓存条目数量，表示缓存最近的n次搜索结果，0表示不缓存。缓存保存在内存中。图片搜索和视频搜索分开缓存。重启程序或扫描完成会清空缓存，或前端点击清空缓存（前端按钮已隐藏）。
POSITIVE_THRESHOLD = int(os.getenv('POSITIVE_THRESHOLD', 36))  # 正向搜索词搜出来的素材，高于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
NEGATIVE_THRESHOLD = int(os.getenv('NEGATIVE_THRESHOLD', 36))  # 反向搜索词搜出来的素材，低于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
IMAGE_THRESHOLD = int(os.getenv('IMAGE_THRESHOLD', 85))  # 图片搜出来的素材，高于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）

# *****日志配置*****
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')  # 日志等级：NOTSET/DEBUG/INFO/WARNING/ERROR/CRITICAL

# *****其它配置*****
SQLALCHEMY_DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URL', 'sqlite:///./instance/assets.db')  # 数据库保存路径
TEMP_PATH = os.getenv('TEMP_PATH', './tmp')  # 临时目录路径
VIDEO_EXTENSION_LENGTH = int(os.getenv('VIDEO_EXTENSION_LENGTH', 0))  # 下载视频片段时，视频前后增加的时长，单位为秒
ENABLE_LOGIN = os.getenv('ENABLE_LOGIN', 'False').lower() == 'true'  # 是否启用登录
USERNAME = os.getenv('USERNAME', 'admin')  # 登录用户名
PASSWORD = os.getenv('PASSWORD', 'MaterialSearch')  # 登录密码
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'  # flask 调试开关（热重载）
ENABLE_CHECKSUM = os.getenv('ENABLE_CHECKSUM', 'False').lower() == 'true'  # 是否启用文件校验（如果是，则通过文件校验来判断文件是否更新，否则通过修改时间判断）

# *****DEVICE处理*****
if DEVICE == 'auto':  # 自动选择设备，优先级：cuda > xpu > mps > directml > cpu
    if torch.cuda.is_available():
        DEVICE = 'cuda'
    elif hasattr(torch, 'xpu') and torch.xpu.is_available():
        DEVICE = 'xpu'
    elif torch.backends.mps.is_available():
        DEVICE = 'mps'
    elif importlib.util.find_spec("torch_directml") is not None:
        try:
            import torch_directml

            if torch_directml.device_count() > 0:
                DEVICE = torch_directml.device()
                x = torch.rand((1, 1), device=DEVICE)  # 测试是否可用
                x = 1.0 - x
            else:
                DEVICE = 'cpu'
        except Exception as e:
            # print(f"经检测，不支持使用directml加速({repr(e)})，因此使用CPU:")
            DEVICE = 'cpu'
    else:
        DEVICE = 'cpu'

# *****打印配置内容*****
print("********** 运行配置 / RUNNING CONFIGURATIONS **********")
global_vars = globals().copy()
for var_name, var_value in global_vars.items():
    if "i" in var_name and "I" in var_name: continue
    if var_name[0].isupper():
        print(f"{var_name}: {var_value!r}")
print(f"HF_HOME: {os.getenv('HF_HOME')}")
print(f"HF_HUB_OFFLINE: {os.getenv('HF_HUB_OFFLINE')}")
print(f"TRANSFORMERS_OFFLINE: {os.getenv('TRANSFORMERS_OFFLINE')}")
print(f"CWD: {os.getcwd()}")
print("**************************************************")
