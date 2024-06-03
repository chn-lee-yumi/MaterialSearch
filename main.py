import base64
import logging
import shutil
import threading
from functools import wraps
from io import BytesIO

from flask import Flask, abort, jsonify, redirect, request, send_file, session, url_for

from config import *
from database import get_image_path_by_id, is_video_exist, get_pexels_video_count
from models import DatabaseSession, DatabaseSessionPexelsVideo
from process_assets import match_text_and_image, process_image, process_text
from scan import Scanner
from search import (
    clean_cache,
    search_image_by_image,
    search_image_by_text,
    search_image_file,
    search_video_by_image,
    search_video_by_text,
    search_video_file,
    search_pexels_video_by_text,
)
from utils import crop_video, get_hash, resize_image_with_aspect_ratio

logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "https://github.com/chn-lee-yumi/MaterialSearch"

scanner = Scanner()


def init():
    """
    清理和创建临时文件夹，初始化扫描线程（包括数据库初始化），根据AUTO_SCAN决定是否开启自动扫描线程
    """
    global scanner
    # 删除上传目录中所有文件
    shutil.rmtree(f'{TEMP_PATH}/upload', ignore_errors=True)
    os.makedirs(f'{TEMP_PATH}/upload')
    shutil.rmtree(f'{TEMP_PATH}/video_clips', ignore_errors=True)
    os.makedirs(f'{TEMP_PATH}/video_clips')
    # 初始化扫描线程
    scanner.init()
    if AUTO_SCAN:
        auto_scan_thread = threading.Thread(target=scanner.auto_scan, args=())
        auto_scan_thread.start()


def login_required(view_func):
    """
    装饰器函数，用于控制需要登录认证的视图
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # 检查登录开关状态
        if ENABLE_LOGIN:
            # 如果开关已启用，则进行登录认证检查
            if "username" not in session:
                # 如果用户未登录，则重定向到登录页面
                return redirect(url_for("login"))
        # 调用原始的视图函数
        return view_func(*args, **kwargs)

    return wrapper


@app.route("/", methods=["GET"])
@login_required
def index_page():
    """主页"""
    return app.send_static_file("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """登录"""
    if request.method == "POST":
        # 获取用户IP地址
        ip_addr = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)
        # 获取表单数据
        username = request.form["username"]
        password = request.form["password"]
        # 简单的验证逻辑
        if username == USERNAME and password == PASSWORD:
            # 登录成功，将用户名保存到会话中
            logger.info(f"用户登录成功 {ip_addr}")
            session["username"] = username
            return redirect(url_for("index_page"))
        # 登录失败，重定向到登录页面
        logger.info(f"用户登录失败 {ip_addr}")
        return redirect(url_for("login"))
    return app.send_static_file("login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    """登出"""
    # 清除会话数据
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/scan", methods=["GET"])
@login_required
def api_scan():
    """开始扫描"""
    global scanner
    if not scanner.is_scanning:
        scan_thread = threading.Thread(target=scanner.scan, args=(False,))
        scan_thread.start()
        return jsonify({"status": "start scanning"})
    return jsonify({"status": "already scanning"})


@app.route("/api/status", methods=["GET"])
@login_required
def api_status():
    """状态"""
    global scanner
    result = scanner.get_status()
    with DatabaseSessionPexelsVideo() as session:
        result["total_pexels_videos"] = get_pexels_video_count(session)
    return jsonify(result)


@app.route("/api/clean_cache", methods=["GET", "POST"])
@login_required
def api_clean_cache():
    """
    清缓存
    :return: 204 No Content
    """
    clean_cache()
    return "", 204


@app.route("/api/match", methods=["POST"])
@login_required
def api_match():
    """
    匹配文字对应的素材
    :return: json格式的素材信息列表
    """
    data = request.get_json()
    top_n = int(data["top_n"])
    search_type = data["search_type"]
    positive_threshold = data["positive_threshold"]
    negative_threshold = data["negative_threshold"]
    image_threshold = data["image_threshold"]
    img_id = data["img_id"]
    path = data["path"]
    upload_file_path = session.get('upload_file_path', '')
    session['upload_file_path'] = ""
    if search_type in (1, 3, 4):
        if not upload_file_path or not os.path.exists(upload_file_path):
            return "你没有上传文件！", 400
    logger.debug(data)
    # 进行匹配
    if search_type == 0:  # 文字搜图
        results = search_image_by_text(data["positive"], data["negative"], positive_threshold, negative_threshold)
    elif search_type == 1:  # 以图搜图
        results = search_image_by_image(upload_file_path, image_threshold)
    elif search_type == 2:  # 文字搜视频
        results = search_video_by_text(data["positive"], data["negative"], positive_threshold, negative_threshold)
    elif search_type == 3:  # 以图搜视频
        results = search_video_by_image(upload_file_path, image_threshold)
    elif search_type == 4:  # 图文相似度匹配
        score = match_text_and_image(process_text(data["text"]), process_image(upload_file_path)) * 100
        return jsonify({"score": "%.2f" % score})
    elif search_type == 5:  # 以图搜图(图片是数据库中的)
        results = search_image_by_image(img_id, image_threshold)
    elif search_type == 6:  # 以图搜视频(图片是数据库中的)
        results = search_video_by_image(img_id, image_threshold)
    elif search_type == 7:  # 路径搜图
        results = search_image_file(path)
    elif search_type == 8:  # 路径搜视频
        results = search_video_file(path)
    elif search_type == 9:  # 文字搜pexels视频
        results = search_pexels_video_by_text(data["positive"], positive_threshold)
    else:  # 空
        logger.warning(f"search_type不正确：{search_type}")
        abort(400)
    return jsonify(results[:top_n])


@app.route("/api/get_image/<int:image_id>", methods=["GET"])
@login_required
def api_get_image(image_id):
    """
    读取图片
    :param image_id: int, 图片在数据库中的id
    :return: 图片文件
    """
    with DatabaseSession() as session:
        path = get_image_path_by_id(session, image_id)
        logger.debug(path)
    # 静态图片压缩返回
    if request.args.get("thumbnail") and os.path.splitext(path)[-1] != "gif":
        image = resize_image_with_aspect_ratio(path, (640, 480), convert_rgb=True)
        image_io = BytesIO()
        image.save(image_io, 'JPEG', quality=60)
        image_io.seek(0)
        return send_file(image_io, mimetype='image/jpeg')
    return send_file(path)


@app.route("/api/get_video/<video_path>", methods=["GET"])
@login_required
def api_get_video(video_path):
    """
    读取视频
    :param video_path: string, 经过base64.urlsafe_b64encode的字符串，解码后可以得到视频在服务器上的绝对路径
    :return: 视频文件
    """
    path = base64.urlsafe_b64decode(video_path).decode()
    logger.debug(path)
    with DatabaseSession() as session:
        if not is_video_exist(session, path):  # 如果路径不在数据库中，则返回404，防止任意文件读取攻击
            abort(404)
    return send_file(path)


@app.route(
    "/api/download_video_clip/<video_path>/<int:start_time>/<int:end_time>",
    methods=["GET"],
)
@login_required
def api_download_video_clip(video_path, start_time, end_time):
    """
    下载视频片段
    :param video_path: string, 经过base64.urlsafe_b64encode的字符串，解码后可以得到视频在服务器上的绝对路径
    :param start_time: int, 视频开始秒数
    :param end_time: int, 视频结束秒数
    :return: 视频文件
    """
    path = base64.urlsafe_b64decode(video_path).decode()
    logger.debug(path)
    with DatabaseSession() as session:
        if not is_video_exist(session, path):  # 如果路径不在数据库中，则返回404，防止任意文件读取攻击
            abort(404)
    # 根据VIDEO_EXTENSION_LENGTH调整时长
    start_time -= VIDEO_EXTENSION_LENGTH
    end_time += VIDEO_EXTENSION_LENGTH
    if start_time < 0:
        start_time = 0
    # 调用ffmpeg截取视频片段
    output_path = f"{TEMP_PATH}/video_clips/{start_time}_{end_time}_" + os.path.basename(path)
    if not os.path.exists(output_path):  # 如果存在说明已经剪过，直接返回，如果不存在则剪
        crop_video(path, output_path, start_time, end_time)
    return send_file(output_path)


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    """
    上传文件。首先删除旧的文件，保存新文件，计算hash，重命名文件。
    :return: 200
    """
    logger.debug(request.files)
    # 删除旧文件
    upload_file_path = session.get('upload_file_path', '')
    if upload_file_path and os.path.exists(upload_file_path):
        os.remove(upload_file_path)
    # 保存文件
    f = request.files["file"]
    filehash = get_hash(f.stream)
    upload_file_path = f"{TEMP_PATH}/upload/{filehash}"
    f.save(upload_file_path)
    session['upload_file_path'] = upload_file_path
    return "file uploaded successfully"


if __name__ == "__main__":
    init()
    logging.getLogger('werkzeug').setLevel(LOG_LEVEL)
    app.run(port=PORT, host=HOST, debug=FLASK_DEBUG)
