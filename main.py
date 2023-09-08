import base64
import logging
import pickle
import threading
import time
from functools import lru_cache, wraps

import numpy as np
from flask import abort, jsonify, redirect, request, send_file, session, url_for
from sqlalchemy import asc

from app_base import app
from config import *
from database import Image, Video, db
from process_assets import (
    match_batch,
    match_text_and_image,
    process_image,
    process_text,
    process_video,
)
from scan import Scanner
from utils import crop_video, get_file_hash, softmax

logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

scanner = Scanner(app, db)
upload_file_path = ""


def optimize_db():
    """
    更新数据库的feature列，从pickle保存改成numpy保存
    本功能为临时功能，几个月后会移除（默认大家后面都已经全部迁移好了）
    :return: None
    """
    with app.app_context():
        total_images = db.session.query(Image).count()
        total_videos = db.session.query(Video.path).distinct().count()
        image = db.session.query(Image).first()
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
            for file in db.session.query(Image):
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
        scanner.total_images = db.session.query(Image).count()  # 获取图片总数
        scanner.total_videos = db.session.query(Video.path).distinct().count()  # 获取视频总数
        scanner.total_video_frames = db.session.query(Video).count()  # 获取视频帧总数
    if not os.path.exists(TEMP_PATH):  # 如果临时文件夹不存在，则创建
        os.mkdir(TEMP_PATH)
    optimize_db()  # 数据库优化（临时功能）
    if AUTO_SCAN:
        auto_scan_thread = threading.Thread(target=scanner.auto_scan, args=())
        auto_scan_thread.start()


def clean_cache():
    """
    清空搜索缓存
    :return: None
    """
    search_image_by_text.cache_clear()
    search_image_by_image.cache_clear()
    search_video_by_text.cache_clear()
    search_video_by_image.cache_clear()
    search_file.cache_clear()


def search_image_by_feature(
    positive_feature,
    negative_feature=None,
    positive_threshold=POSITIVE_THRESHOLD,
    negative_threshold=NEGATIVE_THRESHOLD,
):
    """
    通过特征搜索图片
    :param positive_feature: np.array, 正向特征向量
    :param negative_feature: np.array, 反向特征向量
    :param positive_threshold: int/float, 正向阈值
    :param negative_threshold: int/float, 反向阈值
    :return: list[dict], 搜索结果列表
    """
    scores_list = []
    t0 = time.time()
    with app.app_context():
        image_features = []
        file_list = []
        for file in db.session.query(Image):
            features = np.frombuffer(file.features, dtype=np.float32).reshape(1, -1)
            if features is None:  # 内容损坏，删除该条记录
                db.session.delete(file)
                db.session.commit()
                continue
            file_list.append(file)
            image_features.append(features)
        if len(image_features) == 0:  # 没有素材，直接返回空
            return []
        scores = match_batch(
            positive_feature,
            negative_feature,
            image_features,
            positive_threshold,
            negative_threshold,
        )
        for i in range(len(file_list)):
            if not scores[i]:
                continue
            scores_list.append(
                {
                    "url": "api/get_image/%d" % file_list[i].id,
                    "path": file_list[i].path,
                    "score": float(scores[i]),
                }
            )
    logger.info("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


def search_image_by_text(
    positive_prompt="",
    negative_prompt="",
    positive_threshold=POSITIVE_THRESHOLD,
    negative_threshold=NEGATIVE_THRESHOLD,
):
    """
    使用文字搜图片
    :param positive_prompt: string, 正向提示词
    :param negative_prompt: string, 反向提示词
    :param positive_threshold: int/float, 正向阈值
    :param negative_threshold: int/float, 反向阈值
    :return: list[dict], 搜索结果列表
    """
    positive_feature = process_text(positive_prompt)
    negative_feature = process_text(negative_prompt)
    return search_image_by_feature(
        positive_feature, negative_feature, positive_threshold, negative_threshold
    )


@lru_cache(maxsize=CACHE_SIZE)
def search_image_by_image(img_id_or_path, threshold=IMAGE_THRESHOLD):
    """
    使用图片搜图片
    :param img_id_or_path: int/string, 图片ID 或 图片路径
    :param threshold: int/float, 搜索阈值
    :return: list[dict], 搜索结果列表
    """
    try:
        img_id = int(img_id_or_path)
    except ValueError as e:
        img_path = img_id_or_path
    if img_id:
        with app.app_context():
            image = db.session.query(Image).filter_by(id=img_id).first()
            if not image:
                logger.warning("用数据库的图来进行搜索，但id在数据库中不存在")
                return []
            feature = np.frombuffer(image.features, dtype=np.float32).reshape(1, -1)
    elif img_path:
        feature = process_image(img_path)
    return search_image_by_feature(feature, None, threshold)


def get_index_pairs(scores):
    """
    根据每一帧的余弦相似度计算素材片段
    :param scores: [<class 'numpy.nparray'>], 余弦相似度列表，里面每个元素的shape=(1, 1)
    :return: 返回连续的帧序号列表，如第2-5帧、第11-13帧都符合搜索内容，则返回[(2,5),(11,13)]
    """
    indexes = []
    for i in range(len(scores)):
        if scores[i]:
            indexes.append(i)
    result = []
    start_index = -1
    for i in range(len(indexes)):
        if start_index == -1:
            start_index = indexes[i]
        elif indexes[i] - indexes[i - 1] > 2:  # 允许中间空1帧
            result.append((start_index, indexes[i - 1]))
            start_index = indexes[i]
    if start_index != -1:
        result.append((start_index, indexes[-1]))
    return result


def search_video_by_feature(
    positive_feature,
    negative_feature=None,
    positive_threshold=POSITIVE_THRESHOLD,
    negative_threshold=NEGATIVE_THRESHOLD,
):
    """
    通过特征搜索视频
    :param positive_feature: np.array, 正向特征向量
    :param negative_feature: np.array, 反向特征向量
    :param positive_threshold: int/float, 正向阈值
    :param negative_threshold: int/float, 反向阈值
    :return: list[dict], 搜索结果列表
    """
    t0 = time.time()
    scores_list = []
    with app.app_context():
        for path in db.session.query(Video.path).distinct():  # 逐个视频比对
            path = path[0]
            frames = (
                db.session.query(Video)
                .filter_by(path=path)
                .order_by(Video.frame_time)
                .all()
            )
            image_features = list(
                map(
                    lambda x: np.frombuffer(x.features, dtype=np.float32).reshape(
                        1, -1
                    ),
                    frames,
                )
            )
            scores = match_batch(
                positive_feature,
                negative_feature,
                image_features,
                positive_threshold,
                negative_threshold,
            )
            index_pairs = get_index_pairs(scores)
            for start_index, end_index in index_pairs:
                # 间隔小于等于2倍FRAME_INTERVAL的算为同一个素材，同时开始时间和结束时间各延长0.5个FRAME_INTERVAL
                score = max(scores[start_index : end_index + 1])
                if start_index > 0:
                    start_time = int(
                        (
                            frames[start_index].frame_time
                            + frames[start_index - 1].frame_time
                        )
                        / 2
                    )
                else:
                    start_time = frames[start_index].frame_time
                if end_index < len(scores) - 1:
                    end_time = int(
                        (
                            frames[end_index].frame_time
                            + frames[end_index + 1].frame_time
                        )
                        / 2
                        + 0.5
                    )
                else:
                    end_time = frames[end_index].frame_time
                scores_list.append(
                    {
                        "url": "api/get_video/%s"
                        % base64.urlsafe_b64encode(path.encode()).decode()
                        + "#t=%.1f,%.1f" % (start_time, end_time),
                        "path": path,
                        "score": score,
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                )
    logger.info("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


@lru_cache(maxsize=CACHE_SIZE)
def search_video_by_text(
    positive_prompt="",
    negative_prompt="",
    positive_threshold=POSITIVE_THRESHOLD,
    negative_threshold=NEGATIVE_THRESHOLD,
):
    """
    使用文字搜视频
    :param positive_prompt: string, 正向提示词
    :param negative_prompt: string, 反向提示词
    :param positive_threshold: int/float, 正向阈值
    :param negative_threshold: int/float, 反向阈值
    :return: list[dict], 搜索结果列表
    """
    positive_feature = process_text(positive_prompt)
    negative_feature = process_text(negative_prompt)
    return search_video_by_feature(
        positive_feature, negative_feature, positive_threshold, negative_threshold
    )


@lru_cache(maxsize=CACHE_SIZE)
def search_video_by_image(img_id_or_path, threshold=IMAGE_THRESHOLD):
    """
    使用图片搜视频
    :param img_id_or_path: int/string, 图片ID 或 图片路径
    :param threshold: int/float, 搜索阈值
    :return: list[dict], 搜索结果列表
    """
    try:
        img_id = int(img_id_or_path)
    except ValueError as e:
        img_path = img_id_or_path
    if img_id:
        with app.app_context():
            image = db.session.query(Image).filter_by(id=img_id).first()
            if not image:
                logger.warning("用数据库的图来进行搜索，但id在数据库中不存在")
                return []
            feature = np.frombuffer(image.features, dtype=np.float32).reshape(1, -1)
    elif img_path:
        feature = process_image(img_path)
    return search_video_by_feature(feature, None, threshold)


@lru_cache(maxsize=CACHE_SIZE)
def search_file(path, file_type):
    """
    通过路径搜索图片或视频
    :param path: 路径
    :param file_type: 文件类型，"image"或"video"
    :return:
    """
    if file_type == "image":
        files = (
            db.session.query(Image)
            .filter(Image.path.like("%" + path + "%"))
            .order_by(asc(Image.path))
        )
    elif file_type == "video":
        files = (
            db.session.query(Video.path)
            .distinct()
            .filter(Video.path.like("%" + path + "%"))
            .order_by(asc(Video.path))
        )
    else:
        abort(400)
    file_list = []
    for file in files:
        if file_type == "image":
            file_list.append({"url": "api/get_image/%d" % file.id, "path": file.path})
        elif file_type == "video":
            file_list.append(
                {
                    "url": "api/get_video/%s"
                    % base64.urlsafe_b64encode(file.path.encode()).decode(),
                    "path": file.path,
                }
            )
    return file_list


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
        scan_thread = threading.Thread(target=scanner.scan, args=(False,))
        scan_thread.start()
        return jsonify({"status": "start scanning"})
    return jsonify({"status": "already scanning"})


@app.route("/api/status", methods=["GET"])
@login_required
def api_status():
    """状态"""
    global scanner
    if scanner.scanned_files:
        remain_time = (
            (time.time() - scanner.scan_start_time)
            / scanner.scanned_files
            * scanner.scanning_files
        )
    else:
        remain_time = 0
    if scanner.is_scanning and scanner.scanning_files != 0:
        progress = scanner.scanned_files / scanner.scanning_files
    else:
        progress = 0
    return jsonify(
        {
            "status": scanner.is_scanning,
            "total_images": scanner.total_images,
            "total_videos": scanner.total_videos,
            "total_video_frames": scanner.total_video_frames,
            "scanning_files": scanner.scanning_files,
            "remain_files": scanner.scanning_files - scanner.scanned_files,
            "progress": progress,
            "remain_time": int(remain_time),
            "enable_login": ENABLE_LOGIN,
        }
    )


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
        return jsonify(
            {
                "score": "%.2f"
                % (
                    match_text_and_image(
                        process_text(data["text"]), process_image(upload_file_path)
                    )
                    * 100
                )
            }
        )
    elif search_type == 5:  # 以图搜图(图片是数据库中的)
        sorted_list = search_image_by_image(img_id, image_threshold)[:MAX_RESULT_NUM]
    elif search_type == 6:  # 以图搜视频(图片是数据库中的)
        sorted_list = search_video_by_image(img_id, image_threshold)[:MAX_RESULT_NUM]
    elif search_type == 7:  # 路径搜图
        return jsonify(search_file(path=path, file_type="image")[:top_n])
    elif search_type == 8:  # 路径搜视频
        return jsonify(search_file(path=path, file_type="video")[:top_n])
    else:  # 空
        abort(400)
    sorted_list = sorted_list[:top_n]
    scores = [item["score"] for item in sorted_list]
    softmax_scores = softmax(scores)
    if search_type in (0, 1, 5):
        new_sorted_list = [
            {
                "url": item["url"],
                "path": item["path"],
                "score": "%.2f" % (item["score"] * 100),
                "softmax_score": "%.2f%%" % (score * 100),
            }
            for item, score in zip(sorted_list, softmax_scores)
        ]
    else:  # search_type in (2, 3, 6)
        new_sorted_list = [
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
    return jsonify(new_sorted_list)


@app.route("/api/get_image/<int:image_id>", methods=["GET"])
@login_required
def api_get_image(image_id):
    """
    读取图片
    :param image_id: int, 图片在数据库中的id
    :return: 图片文件
    """
    with app.app_context():
        file = db.session.query(Image).filter_by(id=image_id).first()
        logger.debug(file.path)
    return send_file(file.path)


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
        video = db.session.query(Video).filter_by(path=path).first()
        if not video:  # 如果路径不在数据库中，则返回404，防止任意文件读取攻击
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
        video = db.session.query(Video).filter_by(path=path).first()
        if not video:  # 如果路径不在数据库中，则返回404，防止任意文件读取攻击
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
