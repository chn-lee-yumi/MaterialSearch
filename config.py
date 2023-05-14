# *****扫描配置*****
AUTO_SCAN = False  # 是否在启动时进行一次扫描
ASSETS_PATH = (
    r"/",
)  # 素材所在的目录，绝对路径
SKIP_PATH = (
    r'/tmp'
)  # 跳过扫描的目录，绝对路径
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif")  # 支持的图片拓展名
VIDEO_EXTENSIONS = (".mp4", ".flv", ".mov", ".mkv")  # 支持的视频拓展名
IGNORE_STRINGS = ("thumb", "avatar", "thumb", "icon", "cache")  # 如果路径或文件名包含这些字符串，就跳过（先把字符串转小写再对比）
FRAME_INTERVAL = 2  # 视频每隔多少秒取一帧，视频展示的时候，间隔小于等于2倍FRAME_INTERVAL的算为同一个素材，同时开始时间和结束时间各延长0.5个FRAME_INTERVAL
IMAGE_MIN_WIDTH = 64  # 图片最小宽度，低于此宽度则不进行计算
IMAGE_MIN_HEIGHT = 64  # 图片最小高度，低于此宽度则不进行计算

# *****模型配置*****
LANGUAGE = "Chinese"  # 模型搜索时用的语言，可选：Chinese/English
MODEL_NAME = "openai/clip-vit-base-patch32"  # 显存大于等于4G可用 openai/clip-vit-large-patch14 注意更换模型后需要删库重扫，否则搜索出错
TEXT_MODEL_NAME = "IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese"  # 显存大于等于4G可用 IDEA-CCNL/Taiyi-CLIP-Roberta-large-326M-Chinese 注意这两个模型是配套使用的，如果不需要英文
DEVICE = "cpu"  # 推理设备，cpu/cuda/mps，建议先跑benchmark.py看看cpu还是显卡速度更快，因为数据搬运也需要时间
DEVICE_TEXT = "cpu"  # text_encoder使用的设备，如果使用英文模型，则忽略该项设置。英文模型的图像和文字处理都用DEVICE。

# *****搜索配置*****
ENABLE_CACHE = True  # 是否启用搜索缓存（重新扫描会清空缓存，或前端点击清空缓存）
MAX_RESULT_NUM = 150  # 最大搜索出来的结果数量，如果需要改大这个值，目前还需要手动修改前端代码（前端代码写死最大150）
POSITIVE_THRESHOLD = 10  # 正向搜索词搜出来的素材，高于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
NEGATIVE_THRESHOLD = 10  # 反向搜索词搜出来的素材，低于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
IMAGE_THRESHOLD = 85  # 图片搜出来的素材，高于这个分数才展示。这个是默认值，用的时候可以在前端修改。（前端代码也写死了这个默认值）
