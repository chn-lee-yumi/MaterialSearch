import logging
import shutil
import threading

import routes
from config import *
from init import *
from scan import scanner

logger = logging.getLogger(__name__)


def init():
    """
    清理和创建临时文件夹，初始化扫描线程（包括数据库初始化），根据AUTO_SCAN决定是否开启自动扫描线程
    """
    # 检查ASSETS_PATH是否存在
    for path in ASSETS_PATH:
        if not os.path.isdir(path):
            logger.warning(f"ASSETS_PATH检查：路径 {path} 不存在！请检查输入的路径是否正确！")
    # 删除临时目录中所有文件
    shutil.rmtree(f'{TEMP_PATH}', ignore_errors=True)
    os.makedirs(f'{TEMP_PATH}/upload')
    os.makedirs(f'{TEMP_PATH}/video_clips')
    # 初始化扫描线程
    scanner.init()
    if AUTO_SCAN:
        auto_scan_thread = threading.Thread(target=scanner.auto_scan, args=())
        auto_scan_thread.start()


if __name__ == "__main__":
    pre_init()
    init()
    logging.getLogger('werkzeug').setLevel(LOG_LEVEL)
    post_init()
    routes.app.run(port=PORT, host=HOST, debug=FLASK_DEBUG)
