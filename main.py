import base64
import logging
import pickle
import threading
from functools import wraps

from flask import abort, jsonify, redirect, request, send_file, session, url_for

from app_base import app
from config import *
import crud
from database import Video, db
from process_assets import match_text_and_image, process_image, process_text
from scan import Scanner
from search import (
    clean_cache,
    search_file,
    search_image_by_image,
    search_image_by_text,
    search_video_by_image,
    search_video_by_text,
)
from utils import crop_video, get_file_hash, softmax

logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

scanner = Scanner()
upload_file_path = ""


def optimize_db():
    """
    更新数据库的feature列，从pickle保存改成numpy保存
    本功能为临时功能，几个月后会移除（默认大家后面都已经全部迁移好了）
    :return: None
    """
    with app.app_context():
        total_images = crud.get_image_count(db.session)
        total_videos = crud.get_video_count(db.session)
        image = crud.get_image(db.session)
        try:
            pickle.loads(image.features)
        except Exception as e:
            logger.debug(f"optimize_db pickle.loads: {repr(e)}")
            logger.info("数据库已经优化过")
            return
        else:
            logger.info("开始优化数据库，切勿中断，否则要删库重扫！如果你文件数量多，可能比较久。")
            logger.info("参考速度：5万图片+200个视频（100万视频帧），在J3455上大约需要15分钟。")
            i = 0
            for file in crud.get_images(db.session):
                features = pickle.loads(file.features)
                if features is None:
                    db.session.delete(file)
                else:
                    file.features = features.tobytes()
                i += 1
                print(f"\rprocessing images: {i}/{total_images}", end="")
                if i % 1000 == 0:
                    db.session.commit()
            db.session.commit()
            print()
            i = 0
            for path in db.session.query(Video.path).distinct():
                path = path[0]
                for file in db.session.query(Video).filter_by(path=path):
                    features = pickle.loads(file.features)
                    if features is None:
                        db.session.delete(file)
                    else:
                        file.features = features.tobytes()
                i += 1
                print(f"\rprocessing videos: {i}/{total_videos}", end="")
                db.session.commit()
            db.session.commit()
            logger.info(f"数据库优化完成")


def init():
    """
    初始化数据库，创建临时文件夹，根据AUTO_SCAN决定是否开启自动扫描线程
    :return: None
    """
    global scanner
    with app.app_context():
        db.create_all()  # 初始化数据库
        scanner.init()
    if not os.path.exists(TEMP_PATH):  # 如果临时文件夹不存在，则创建
        os.mkdir(TEMP_PATH)
    optimize_db()  # 数据库优化（临时功能）
    if AUTO_SCAN:
        auto_scan_thread = threading.Thread(target=scanner.auto_scan, args=(app.app_context(), ))
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
    """主页，根据浏览器的语言自动返回中文页面或英文页面"""
    language = request.accept_languages.best_match(["zh", "en"])
    if language == "zh":
        return app.send_static_file("index.html")
    else:
        return app.send_static_file("index_en.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """简单的登录功能"""
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
    return redirect(url_for("index_page"))


@app.route("/api/scan", methods=["GET"])
@login_required
def api_scan():
    """开始扫描"""
    global scanner
    if not scanner.is_scanning:
        # https://stackoverflow.com/questions/72541670/why-flask-app-context-is-lost-in-child-thread-when-application-factory-pattern-i
        scan_thread = threading.Thread(target=scanner.scan, args=(False, app.app_context(), ))
        scan_thread.start()
        return jsonify({"status": "start scanning"})
    return jsonify({"status": "already scanning"})


@app.route("/api/status", methods=["GET"])
@login_required
def api_status():
    """状态"""
    global scanner
    return jsonify(scanner.get_status())


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
    global upload_file_path
    data = request.get_json()
    top_n = int(data["top_n"])
    search_type = data["search_type"]
    positive_threshold = data["positive_threshold"]
    negative_threshold = data["negative_threshold"]
    image_threshold = data["image_threshold"]
    img_id = data["img_id"]
    path = data["path"]
    logger.debug(data)
    if search_type not in (0, 1, 2, 3, 4, 5, 6, 7, 8):
        logger.warning(f"search_type不正确：{search_type}")
        abort(500)
    # 进行匹配
    with app.app_context():
        if search_type == 0:  # 文字搜图
            sorted_list = search_image_by_text(
                data["positive"], data["negative"], positive_threshold, negative_threshold
            )[:MAX_RESULT_NUM]
        elif search_type == 1:  # 以图搜图
            sorted_list = search_image_by_image(upload_file_path, image_threshold)[
                :MAX_RESULT_NUM
            ]
        elif search_type == 2:  # 文字搜视频
            sorted_list = search_video_by_text(
                data["positive"], data["negative"], positive_threshold, negative_threshold
            )[:MAX_RESULT_NUM]
        elif search_type == 3:  # 以图搜视频
            sorted_list = search_video_by_image(upload_file_path, image_threshold)[
                :MAX_RESULT_NUM
            ]
        elif search_type == 4:  # 图文相似度匹配
            score = match_text_and_image(process_text(data["text"]), process_image(upload_file_path)) * 100
            return jsonify({
                    "score": f"{score:.2f}"
                }
            )
        elif search_type == 5:  # 以图搜图(图片是数据库中的)
            sorted_list = search_image_by_image(img_id, image_threshold)[:MAX_RESULT_NUM]
        elif search_type == 6:  # 以图搜视频(图片是数据库中的)
            sorted_list = search_video_by_image(img_id, image_threshold)[:MAX_RESULT_NUM]
        elif search_type == 7:  # 路径搜图
            results = search_file(path=path, file_type="image")[:top_n]
            if not results:
                abort(400)
            return jsonify(results)
        elif search_type == 8:  # 路径搜视频
            results = search_file(path=path, file_type="video")[:top_n]
            if not results:
                abort(400)
            return jsonify(results)
        else:  # 空
            abort(400)
    sorted_list = sorted_list[:top_n]
    scores = [item["score"] for item in sorted_list]
    softmax_scores = softmax(scores)
    if search_type in (0, 1, 5):
        sorted_list = [
            {
                "url": item["url"],
                "path": item["path"],
                "score": "%.2f" % (item["score"] * 100),
                "softmax_score": "%.2f%%" % (score * 100),
            }
            for item, score in zip(sorted_list, softmax_scores)
        ]
    elif search_type in (2, 3, 6):
        sorted_list = [
            {
                "url": item["url"],
                "path": item["path"],
                "score": "%.2f" % (item["score"] * 100),
                "softmax_score": "%.2f%%" % (score * 100),
                "start_time": item["start_time"],
                "end_time": item["end_time"],
            }
            for item, score in zip(sorted_list, softmax_scores)
        ]
    return jsonify(sorted_list)


@app.route("/api/get_image/<int:image_id>", methods=["GET"])
@login_required
def api_get_image(image_id):
    """
    读取图片
    :param image_id: int, 图片在数据库中的id
    :return: 图片文件
    """
    with app.app_context():
        path = crud.get_image_path_by_id(db.session, image_id)
        logger.debug(path)
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
    with app.app_context():
        if not crud.is_video_exist(db.session, path):  # 如果路径不在数据库中，则返回404，防止任意文件读取攻击
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
    TODO: 自动清理剪出来的视频片段，避免占用临时目录太多空间
    :param video_path: string, 经过base64.urlsafe_b64encode的字符串，解码后可以得到视频在服务器上的绝对路径
    :param start_time: int, 视频开始秒数
    :param end_time: int, 视频结束秒数
    :return: 视频文件
    """
    path = base64.urlsafe_b64decode(video_path).decode()
    logger.debug(path)
    with app.app_context():
        if not crud.is_video_exist(db.session, path):  # 如果路径不在数据库中，则返回404，防止任意文件读取攻击
            abort(404)
    # 根据VIDEO_EXTENSION_LENGTH调整时长
    start_time -= VIDEO_EXTENSION_LENGTH
    end_time += VIDEO_EXTENSION_LENGTH
    if start_time < 0:
        start_time = 0
    # 调用ffmpeg截取视频片段
    output_path = f"{TEMP_PATH}/{start_time}_{end_time}_" + os.path.basename(path)
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
    global upload_file_path
    logger.debug(request.files)
    # 删除旧文件
    if os.path.exists(upload_file_path):
        os.remove(upload_file_path)
    # 保存文件
    temp_path = f"{TEMP_PATH}/upload.tmp"
    f = request.files["file"]
    f.save(temp_path)
    # 计算hash并重命名文件
    new_filename = get_file_hash(temp_path)
    upload_file_path = f"{TEMP_PATH}/{new_filename}"
    os.rename(temp_path, upload_file_path)
    return "file uploaded successfully"


if __name__ == "__main__":
    init()
    app.run(port=PORT, host=HOST)
