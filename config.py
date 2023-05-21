# *****扫描配置*****
AUTO_SCAN = False  # 是否在启动时进行一次扫描
ASSETS_PATH = (
    r"/home",
    # r"D:/照片",  # Windows系统用这种写法
)  # 素材所在的目录，绝对路径
SKIP_PATH = (
    r'/tmp'
)  # 跳过扫描的目录，绝对路径
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif")  # 支持的图片拓展名
VIDEO_EXTENSIONS = (".mp4", ".flv", ".mov", ".mkv")  # 支持的视频拓展名
IGNORE_STRINGS = ("thumb", "avatar", "thumb", "icon", "cache")  # 如果路径或文件名包含这些字符串，就跳过（先把字符串转小写再对比）
FRAME_INTERVAL = 2  # 视频每隔多少秒取一帧，视频展示的时候，间隔小于等于2倍FRAME_INTERVAL的算为同一个素材，同时开始时间和结束时间各延长0.5个FRAME_INTERVAL
IMAGE_MIN_WIDTH = 64  # 图片最小宽度，小于此宽度则忽略。不需要可以改成0。
IMAGE_MIN_HEIGHT = 64  # 图片最小高度，小于此高度则忽略。不需要可以改成0。

# *****模型配置*****
# 目前支持中文或英文搜索，只能二选一。英文搜索速度会更快。中文搜索需要额外下载模型，而且搜索英文或NSFW内容的效果不好。
# 更换模型需要删库重新扫描，否则搜索会报错。数据库名字为assets.db。切换语言或设备不需要删库，重启程序即可。
# TEXT_MODEL_NAME 仅在中文搜索时需要，模型需要和 MODEL_NAME 配套。
# 显存小于4G使用： "openai/clip-vit-base-patch32" 和 "IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese"
# 显存大于等于4G使用："openai/clip-vit-large-patch14" 和 "IDEA-CCNL/Taiyi-CLIP-Roberta-large-326M-Chinese"
LANGUAGE = "Chinese"  # 模型搜索时用的语言，可选：Chinese/English
MODEL_NAME = "openai/clip-vit-base-patch32"  # CLIP模型
TEXT_MODEL_NAME = "IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese"  # 中文模型，需要和CLIP模型配套使用，如果LANGUAGE为English则忽略此项
DEVICE = "cpu"  # 推理设备，cpu/cuda/mps，建议先跑benchmark.py看看cpu还是显卡速度更快。因为数据搬运也需要时间，所以不一定是GPU更快。
DEVICE_TEXT = "cpu"  # text_encoder使用的设备，如果LANGUAGE为English则忽略此项。

# *****搜索配置*****
# 不知道为什么中文模型搜索出来的分数比较低，如果使用英文模型，则POSITIVE_THRESHOLD和NEGATIVE_THRESHOLD可以上调到30。
ENABLE_CACHE = True  # 是否启用搜索缓存。重启程序或点击扫描会清空缓存，或前端点击清空缓存（前端按钮已隐藏）。
MAX_RESULT_NUM = 150  # 最大搜索出来的结果数量，如果需要改大这个值，目前还需要手动修改前端代码（前端代码写死最大150）
POSITIVE_THRESHOLD = 10  # 正向搜索词搜出来的素材，高于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
NEGATIVE_THRESHOLD = 10  # 反向搜索词搜出来的素材，低于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
IMAGE_THRESHOLD = 85  # 图片搜出来的素材，高于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）

# *****日志配置*****
LOG_LEVEL = "INFO"  # 日志等级：NOTSET/DEBUG/INFO/WARNING/ERROR/CRITICAL

# *****其它配置*****
UPLOAD_TMP_FILE = "upload.tmp"  # 上传图片的保存路径
