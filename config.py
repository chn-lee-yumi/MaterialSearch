import os

from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# *****服务器配置*****
HOST = os.getenv('HOST', '0.0.0.0')  # 监听IP，如果只想本地访问，把这个改成127.0.0.1
PORT = int(os.getenv('PORT', 8085))  # 监听端口

# *****扫描配置*****
# Windows系统的路径写法例子：'D:/照片'
ASSETS_PATH = tuple(os.getenv('ASSETS_PATH', '/home,/srv').split(','))  # 素材所在的目录，绝对路径，逗号分隔
SKIP_PATH = tuple(os.getenv('SKIP_PATH', '/tmp').split(','))  # 跳过扫描的目录，绝对路径，逗号分隔
IMAGE_EXTENSIONS = tuple(os.getenv('IMAGE_EXTENSIONS', '.jpg,.jpeg,.png,.gif').split(','))  # 支持的图片拓展名，逗号分隔，请填小写
VIDEO_EXTENSIONS = tuple(os.getenv('VIDEO_EXTENSIONS', '.mp4,.flv,.mov,.mkv').split(','))  # 支持的视频拓展名，逗号分隔，请填小写
IGNORE_STRINGS = tuple(os.getenv('IGNORE_STRINGS', 'thumb,avatar,__MACOSX,icons,cache').lower().split(','))  # 如果路径或文件名包含这些字符串，就跳过，逗号分隔，不区分大小写
FRAME_INTERVAL = int(os.getenv('FRAME_INTERVAL', 2))  # 视频每隔多少秒取一帧，视频展示的时候，间隔小于等于2倍FRAME_INTERVAL的算为同一个素材，同时开始时间和结束时间各延长0.5个FRAME_INTERVAL
SCAN_PROCESS_BATCH_SIZE = int(os.getenv('SCAN_PROCESS_BATCH_SIZE', 32))  # 等读取的帧数到这个数量后再一次性输入到模型中进行批量计算，从而提高效率
IMAGE_MIN_WIDTH = int(os.getenv('IMAGE_MIN_WIDTH', 64))  # 图片最小宽度，小于此宽度则忽略。不需要可以改成0。
IMAGE_MIN_HEIGHT = int(os.getenv('IMAGE_MIN_HEIGHT', 64))  # 图片最小高度，小于此高度则忽略。不需要可以改成0。
AUTO_SCAN = os.getenv('AUTO_SCAN', 'False').lower() == 'true'  # 是否自动扫描，如果开启，则会在指定时间内进行扫描
AUTO_SCAN_START_TIME = tuple(map(int, os.getenv('AUTO_SCAN_START_TIME', '22:30').split(':')))  # 自动扫描开始时间
AUTO_SCAN_END_TIME = tuple(map(int, os.getenv('AUTO_SCAN_END_TIME', '8:00').split(':')))  # 自动扫描结束时间
AUTO_SAVE_INTERVAL = int(os.getenv('AUTO_SAVE_INTERVAL', 100))  # 扫描自动保存间隔，默认为每 100 个文件自动保存一次

# *****模型配置*****
# 目前支持中文或英文搜索，只能二选一。英文搜索速度会更快。中文搜索需要额外下载模型，而且搜索英文或NSFW内容的效果不好。
# 更换模型需要删库重新扫描，否则搜索会报错。数据库名字为assets.db。切换语言或设备不需要删库，重启程序即可。
# TEXT_MODEL_NAME 仅在中文搜索时需要，模型需要和 MODEL_NAME 配套。
# 显存小于4G使用： "openai/clip-vit-base-patch32" 和 "IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese"
# 显存大于等于4G使用："openai/clip-vit-large-patch14" 和 "IDEA-CCNL/Taiyi-CLIP-Roberta-large-326M-Chinese"
MODEL_LANGUAGE = os.getenv('MODEL_LANGUAGE', 'Chinese')  # 模型搜索时用的语言，可选：Chinese/English
MODEL_NAME = os.getenv('MODEL_NAME', 'openai/clip-vit-base-patch32')  # CLIP模型
TEXT_MODEL_NAME = os.getenv('TEXT_MODEL_NAME', 'IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese')  # 中文模型，需要和CLIP模型配套使用，如果MODEL_LANGUAGE为English则忽略此项
DEVICE = os.getenv('DEVICE', 'cpu')  # 推理设备，cpu/cuda/mps，建议先跑benchmark.py看看cpu还是显卡速度更快。因为数据搬运也需要时间，所以不一定是GPU更快。
DEVICE_TEXT = os.getenv('DEVICE_TEXT', 'cpu')  # text_encoder使用的设备，如果MODEL_LANGUAGE为English则忽略此项。

# *****搜索配置*****
# 不知道为什么中文模型搜索出来的分数比较低，如果使用英文模型，则POSITIVE_THRESHOLD和NEGATIVE_THRESHOLD可以上调到30。
CACHE_SIZE = int(os.getenv('CACHE_SIZE', 64))  # 搜索缓存条目数量，表示缓存最近的n次搜索结果，0表示不缓存。缓存保存在内存中。图片搜索和视频搜索分开缓存。重启程序或扫描完成会清空缓存，或前端点击清空缓存（前端按钮已隐藏）。
MAX_RESULT_NUM = int(os.getenv('MAX_RESULT_NUM', 150))  # 最大搜索出来的结果数量，如果需要改大这个值，目前还需要手动修改前端代码（前端代码写死最大150）
POSITIVE_THRESHOLD = int(os.getenv('POSITIVE_THRESHOLD', 10))  # 正向搜索词搜出来的素材，高于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
NEGATIVE_THRESHOLD = int(os.getenv('NEGATIVE_THRESHOLD', 10))  # 反向搜索词搜出来的素材，低于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
IMAGE_THRESHOLD = int(os.getenv('IMAGE_THRESHOLD', 85))  # 图片搜出来的素材，高于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）

# *****日志配置*****
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')  # 日志等级：NOTSET/DEBUG/INFO/WARNING/ERROR/CRITICAL

# *****其它配置*****
SQLALCHEMY_DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URL', 'sqlite:///assets.db')  # 数据库保存路径
TEMP_PATH = os.getenv('TEMP_PATH', './tmp')  # 临时目录路径
VIDEO_EXTENSION_LENGTH = int(os.getenv('VIDEO_EXTENSION_LENGTH', 0))  # 下载视频片段时，视频前后增加的时长，单位为秒
ENABLE_LOGIN = os.getenv('ENABLE_LOGIN', 'False').lower() == 'true'  # 是否启用登录
USERNAME = os.getenv('USERNAME', 'admin')  # 登录用户名
PASSWORD = os.getenv('PASSWORD', 'MaterialSearch')  # 登录密码
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'  # flask 调试开关（热重载）

# *****打印配置内容*****
print("********** 运行配置 / RUNNING CONFIGURATIONS **********")
global_vars = globals().copy()
for var_name, var_value in global_vars.items():
    if var_name[0].isupper():
        print(f"{var_name}: {var_value!r}")
print("**************************************************")
