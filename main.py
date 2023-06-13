import base64
import datetime
import logging
import os
import pickle
import threading
import time
from functools import lru_cache, wraps

import numpy as np
from flask import Flask, jsonify, request, send_file, abort, session, redirect, url_for

from config import *
from database import db, Image, Video
from process_assets import scan_dir, process_image, process_video, process_text, match_text_and_image, match_batch
from utils import softmax, get_file_hash, crop_video

logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assets.db'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True
app.secret_key = 'https://github.com/chn-lee-yumi/MaterialSearch'
db.init_app(app)

is_scanning = False
scan_start_time = 0
scanning_files = 0
total_images = 0
total_videos = 0
total_video_frames = 0
scanned_files = 0
is_continue_scan = False
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
                print(f"\rprocessing images: {i}/{total_images}", end='')
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
                print(f"\rprocessing videos: {i}/{total_videos}", end='')
                db.session.commit()
            db.session.commit()
            logger.info(f"数据库优化完成")


def init():
    """
    初始化数据库，创建临时文件夹，根据AUTO_SCAN决定是否开启自动扫描线程
    :return: None
    """
    global total_images, total_videos, total_video_frames, is_scanning
    with app.app_context():
        db.create_all()  # 初始化数据库
        total_images = db.session.query(Image).count()  # 获取图片总数
        total_videos = db.session.query(Video.path).distinct().count()  # 获取视频总数
        total_video_frames = db.session.query(Video).count()  # 获取视频帧总数
    if not os.path.exists(TEMP_PATH):  # 如果临时文件夹不存在，则创建
        os.mkdir(TEMP_PATH)
    optimize_db()  # 数据库优化（临时功能）
    if AUTO_SCAN:
        auto_scan_thread = threading.Thread(target=auto_scan, args=())
        auto_scan_thread.start()


def clean_cache():
    """
    清空搜索缓存
    :return: None
    """
    search_image.cache_clear()
    search_video.cache_clear()


def auto_scan():
    """
    自动扫描，每5秒判断一次时间，如果在目标时间段内则开始扫描。
    :return: None
    """
    global is_scanning
    while True:
        time.sleep(5)
        if is_scanning:
            continue
        current_time = datetime.datetime.now().time()
        if datetime.time(*AUTO_SCAN_START_TIME) > datetime.time(*AUTO_SCAN_END_TIME):
            if current_time >= datetime.time(*AUTO_SCAN_START_TIME) or current_time < datetime.time(*AUTO_SCAN_END_TIME):
                logger.info("触发自动扫描")
                scan(auto=True)
        else:
            if datetime.time(*AUTO_SCAN_START_TIME) <= current_time < datetime.time(*AUTO_SCAN_END_TIME):
                logger.info("触发自动扫描")
                scan(auto=True)


def scan(auto=False):
    """
    扫描资源。如果存在assets.pickle，则直接读取并开始扫描。如果不存在，则先读取所有文件路径，并写入assets.pickle，然后开始扫描。
    每100个文件重新保存一次assets.pickle，如果程序被中断，下次可以从断点处继续扫描。扫描完成后删除assets.pickle并清缓存。
    :param auto: 是否由AUTO_SCAN触发的
    :return: None
    """
    global is_scanning, total_images, total_videos, total_video_frames, scanning_files, scanned_files, scan_start_time, is_continue_scan
    logger.info("开始扫描")
    temp_file = f"{TEMP_PATH}/assets.pickle"
    scan_start_time = time.time()
    start_time = time.time()
    if os.path.isfile(temp_file):
        logger.info("读取上次的目录缓存")
        is_continue_scan = True
        with open(temp_file, "rb") as f:
            assets = pickle.load(f)
        for asset in assets.copy():
            if asset.startswith(SKIP_PATH):
                assets.remove(asset)
    else:
        is_continue_scan = False
        assets = scan_dir(ASSETS_PATH, SKIP_PATH, IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)
        with open(f"{TEMP_PATH}/assets.pickle", "wb") as f:
            pickle.dump(assets, f)
    scanning_files = len(assets)
    with app.app_context():
        # 删除不存在的文件记录
        for file in db.session.query(Image):
            if not is_continue_scan and (file.path not in assets or file.path.startswith(SKIP_PATH)):
                logger.info(f"文件已删除：{file.path}")
                db.session.delete(file)
        for path in db.session.query(Video.path).distinct():
            path = path[0]
            if not is_continue_scan and (path not in assets or path.startswith(SKIP_PATH)):
                logger.info(f"文件已删除：{path}")
                db.session.query(Video).filter_by(path=path).delete()
        db.session.commit()
        # 扫描文件
        for asset in assets.copy():
            scanned_files += 1
            if scanned_files % 100 == 0:  # 每扫描100次重新save一下
                with open("assets.pickle", "wb") as f:
                    pickle.dump(assets, f)
            if auto:  # 如果是自动扫描，判断时间自动停止
                current_time = datetime.datetime.now().time()
                if datetime.time(*AUTO_SCAN_START_TIME) > datetime.time(*AUTO_SCAN_END_TIME):
                    if datetime.time(*AUTO_SCAN_END_TIME) <= current_time < datetime.time(*AUTO_SCAN_START_TIME):
                        logger.info(f"超出自动扫描时间，停止扫描")
                        break
                else:
                    if current_time < datetime.time(*AUTO_SCAN_START_TIME) or current_time >= datetime.time(*AUTO_SCAN_END_TIME):
                        logger.info(f"超出自动扫描时间，停止扫描")
                        break
            # 如果文件不存在，则忽略（扫描时文件被移动或删除则会触发这种情况）
            if not os.path.isfile(asset):
                continue
            # 如果数据库里有这个文件，并且修改时间一致，则跳过，否则进行预处理并入库
            if asset.lower().endswith(IMAGE_EXTENSIONS):  # 图片
                db_record = db.session.query(Image).filter_by(path=asset).first()
                modify_time = datetime.datetime.fromtimestamp(os.path.getmtime(asset))
                if db_record and db_record.modify_time == modify_time:
                    logger.debug(f"文件无变更，跳过：{asset}")
                    assets.remove(asset)
                    continue
                features = process_image(asset)
                if features is None:
                    assets.remove(asset)
                    continue
                # 写入数据库
                features = features.tobytes()
                if db_record:
                    logger.info(f"文件有更新：{asset}")
                    db_record.modify_time = modify_time
                    db_record.features = features
                else:
                    logger.info(f"新增文件：{asset}")
                    db.session.add(Image(path=asset, modify_time=modify_time, features=features))
                    total_images = db.session.query(Image).count()  # 获取图片总数
            else:  # 视频
                db_record = db.session.query(Video).filter_by(path=asset).first()
                modify_time = datetime.datetime.fromtimestamp(os.path.getmtime(asset))
                if db_record and db_record.modify_time == modify_time:
                    logger.debug(f"文件无变更，跳过：{asset}")
                    assets.remove(asset)
                    continue
                # 写入数据库
                if db_record:
                    logger.info(f"文件有更新：{asset}")
                    db.session.query(Video).filter_by(path=asset).delete()  # 视频文件直接删了重新写数据，而不是直接替换，因为视频长短可能有变化，不方便处理
                else:
                    logger.info(f"新增文件：{asset}")
                for frame_time, features in process_video(asset):
                    db.session.add(Video(path=asset, frame_time=frame_time, modify_time=modify_time, features=features.tobytes()))
                    total_video_frames = db.session.query(Video).count()  # 获取视频帧总数
                total_videos = db.session.query(Video.path).distinct().count()
            db.session.commit()  # 处理完一张图片或一个完整视频再commit，避免扫描视频到一半时程序中断，下次扫描会跳过这个视频的问题
            assets.remove(asset)
        # 最后重新统计一下数量
        total_images = db.session.query(Image).count()  # 获取图片总数
        total_videos = db.session.query(Video.path).distinct().count()  # 获取视频总数
        total_video_frames = db.session.query(Video).count()  # 获取视频帧总数
    scanning_files = 0
    scanned_files = 0
    os.remove(temp_file)
    logger.info("扫描完成，用时%d秒" % int(time.time() - start_time))
    clean_cache()  # 清空搜索缓存
    is_scanning = False


@lru_cache(maxsize=CACHE_SIZE)
def search_image(positive_prompt="", negative_prompt="", img_path="", img_id=-1,
                 positive_threshold=POSITIVE_THRESHOLD, negative_threshold=NEGATIVE_THRESHOLD, image_threshold=IMAGE_THRESHOLD):
    """
    搜图
    :param positive_prompt: string, 正向提示词
    :param negative_prompt: string, 反向提示词
    :param img_path: string, 图片路径，如果存在，说明是用图搜索，此时忽略提示词
    :param img_id: int, 图片在数据库中的id，如果大于等于0，说明是用数据库的图来进行搜索，此时忽略提示词和img_path
    :param positive_threshold: int/float, 文字搜索阈值，高于此分数才显示
    :param negative_threshold: int/float, 文字过滤阈值，低于此分数才显示
    :param image_threshold: int/float, 以图搜素材匹配阈值，高于这个分数才展示
    :return:
    """
    if img_id >= 0:
        with app.app_context():
            image = db.session.query(Image).filter_by(id=img_id).first()
            if not image:
                logger.warning("用数据库的图来进行搜索，但id在数据库中不存在")
                return []
            positive_feature = np.frombuffer(image.features, dtype=np.float32).reshape(1, -1)
        positive_threshold = image_threshold
        negative_feature = None
    elif img_path:
        positive_feature = process_image(img_path)
        positive_threshold = image_threshold
        negative_feature = None
    else:
        positive_feature = process_text(positive_prompt)
        negative_feature = process_text(negative_prompt)
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
        scores = match_batch(positive_feature, negative_feature, image_features, positive_threshold, negative_threshold)
        for i in range(len(file_list)):
            if not scores[i]:
                continue
            scores_list.append({"url": "api/get_image/%d" % file_list[i].id, "path": file_list[i].path, "score": float(scores[i])})
    logger.info("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


@lru_cache(maxsize=CACHE_SIZE)
def search_video(positive_prompt="", negative_prompt="", img_path="", img_id=-1,
                 positive_threshold=POSITIVE_THRESHOLD, negative_threshold=NEGATIVE_THRESHOLD, image_threshold=IMAGE_THRESHOLD):
    """
    搜视频
    :param positive_prompt: string, 正向提示词
    :param negative_prompt: string, 反向提示词
    :param img_path: string, 图片路径，如果存在，说明是用图搜索，此时忽略提示词
    :param img_id: int, 图片在数据库中的id，如果大于等于0，说明是用数据库的图来进行搜索，此时忽略提示词和img_path
    :param positive_threshold: int/float, 文字搜索阈值，高于此分数才显示
    :param negative_threshold: int/float, 文字过滤阈值，低于此分数才显示
    :param image_threshold: int/float, 以图搜素材匹配阈值，高于这个分数才展示
    :return:
    """
    if img_id >= 0:
        with app.app_context():
            image = db.session.query(Image).filter_by(id=img_id).first()
            if not image:
                logger.warning("用数据库的图来进行搜索，但id在数据库中不存在")
                return []
            positive_feature = np.frombuffer(image.features, dtype=np.float32).reshape(1, -1)
        positive_threshold = image_threshold
        negative_feature = None
    elif img_path:
        positive_feature = process_image(img_path)
        positive_threshold = image_threshold
        negative_feature = None
    else:
        positive_feature = process_text(positive_prompt)
        negative_feature = process_text(negative_prompt)
    scores_list = []
    t0 = time.time()
    with app.app_context():
        for path in db.session.query(Video.path).distinct():  # 逐个视频比对
            path = path[0]
            frames = db.session.query(Video).filter_by(path=path).order_by(Video.frame_time).all()
            image_features = list(map(lambda x: np.frombuffer(x.features, dtype=np.float32).reshape(1, -1), frames))
            scores = match_batch(positive_feature, negative_feature, image_features, positive_threshold, negative_threshold)
            index_pairs = get_index_pairs(scores)
            for index_pair in index_pairs:
                # 间隔小于等于2倍FRAME_INTERVAL的算为同一个素材，同时开始时间和结束时间各延长0.5个FRAME_INTERVAL
                score = max(scores[index_pair[0]:index_pair[1] + 1])
                if index_pair[0] > 0:
                    start_time = int((frames[index_pair[0]].frame_time + frames[index_pair[0] - 1].frame_time) / 2)
                else:
                    start_time = frames[index_pair[0]].frame_time
                if index_pair[1] < len(scores) - 1:
                    end_time = int((frames[index_pair[1]].frame_time + frames[index_pair[1] + 1].frame_time) / 2 + 0.5)
                else:
                    end_time = frames[index_pair[1]].frame_time
                scores_list.append(
                    {"url": "api/get_video/%s" % base64.urlsafe_b64encode(path.encode()).decode() + "#t=%.1f,%.1f" % (
                        start_time, end_time),
                     "path": path, "score": score, "start_time": start_time, "end_time": end_time})
    logger.info("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


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


def login_required(view_func):
    """
    装饰器函数，用于控制需要登录认证的视图
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # 检查登录开关状态
        if ENABLE_LOGIN:
            # 如果开关已启用，则进行登录认证检查
            if 'username' not in session:
                # 如果用户未登录，则重定向到登录页面
                return redirect(url_for('login'))
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
    """简单的登录功能"""
    if request.method == 'POST':
        # 获取用户IP地址
        ip_addr = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        # 获取表单数据
        username = request.form['username']
        password = request.form['password']
        # 简单的验证逻辑
        if username == USERNAME and password == PASSWORD:
            # 登录成功，将用户名保存到会话中
            logger.info(f"用户登录成功 {ip_addr}")
            session['username'] = username
            return redirect(url_for('index_page'))
        # 登录失败，重定向到登录页面
        logger.info(f"用户登录失败 {ip_addr}")
        return redirect(url_for('login'))
    return app.send_static_file("login.html")


@app.route('/logout', methods=["GET", "POST"])
def logout():
    # 清除会话数据
    session.clear()
    return redirect(url_for('index_page'))


@app.route("/api/scan", methods=["GET"])
@login_required
def api_scan():
    """开始扫描"""
    global is_scanning
    if not is_scanning:
        is_scanning = True
        scan_thread = threading.Thread(target=scan, args=(False,))
        scan_thread.start()
        return jsonify({"status": "start scanning"})
    return jsonify({"status": "already scanning"})


@app.route("/api/status", methods=["GET"])
@login_required
def api_status():
    """状态"""
    global is_scanning, scanning_files, scanned_files, scan_start_time, total_images, total_video_frames
    if scanned_files:
        remain_time = (time.time() - scan_start_time) / scanned_files * scanning_files
    else:
        remain_time = 0
    if is_scanning and scanning_files != 0:
        progress = scanned_files / scanning_files
    else:
        progress = 0
    return jsonify({"status": is_scanning, "total_images": total_images, "total_videos": total_videos, "total_video_frames": total_video_frames,
                    "scanning_files": scanning_files, "remain_files": scanning_files - scanned_files, "progress": progress,
                    "remain_time": int(remain_time), "enable_login": ENABLE_LOGIN})


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
    top_n = int(data['top_n'])
    search_type = data['search_type']
    positive_threshold = data['positive_threshold']
    negative_threshold = data['negative_threshold']
    image_threshold = data['image_threshold']
    img_id = data['img_id']
    logger.debug(data)
    if search_type not in (0, 1, 2, 3, 4, 5, 6):
        logger.warning(f"search_type不正确：{search_type}")
        abort(500)
    # 进行匹配
    if search_type == 0:  # 文字搜图
        sorted_list = search_image(positive_prompt=data['positive'], negative_prompt=data['negative'],
                                   positive_threshold=positive_threshold, negative_threshold=negative_threshold)[:MAX_RESULT_NUM]
    elif search_type == 1:  # 以图搜图
        sorted_list = search_image(img_path=upload_file_path, image_threshold=image_threshold)[:MAX_RESULT_NUM]
    elif search_type == 2:  # 文字搜视频
        sorted_list = search_video(positive_prompt=data['positive'], negative_prompt=data['negative'],
                                   positive_threshold=positive_threshold, negative_threshold=negative_threshold)[:MAX_RESULT_NUM]
    elif search_type == 3:  # 以图搜视频
        sorted_list = search_video(img_path=upload_file_path, image_threshold=image_threshold)[:MAX_RESULT_NUM]
    elif search_type == 4:  # 图文相似度匹配
        return jsonify({"score": "%.2f" % (match_text_and_image(process_text(data['text']), process_image(upload_file_path)) * 100)})
    elif search_type == 5:  # 以图搜图(图片是数据库中的)
        sorted_list = search_image(img_id=img_id, image_threshold=image_threshold)[:MAX_RESULT_NUM]
    else:  # search_type == 6 以图搜视频(图片是数据库中的)
        sorted_list = search_video(img_id=img_id, image_threshold=image_threshold)[:MAX_RESULT_NUM]
    sorted_list = sorted_list[:top_n]
    scores = [item["score"] for item in sorted_list]
    softmax_scores = softmax(scores)
    if search_type in (0, 1, 5):
        new_sorted_list = [{
            "url": item["url"], "path": item["path"], "score": "%.2f" % (item["score"] * 100), "softmax_score": "%.2f%%" % (score * 100)
        } for item, score in zip(sorted_list, softmax_scores)]
    else:  # search_type in (2, 3, 6)
        new_sorted_list = [{
            "url": item["url"], "path": item["path"], "score": "%.2f" % (item["score"] * 100), "softmax_score": "%.2f%%" % (score * 100),
            "start_time": item["start_time"], "end_time": item["end_time"]
        } for item, score in zip(sorted_list, softmax_scores)]
    return jsonify(new_sorted_list)


@app.route('/api/get_image/<int:image_id>', methods=['GET'])
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


@app.route('/api/get_video/<video_path>', methods=['GET'])
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


@app.route('/api/download_video_clip/<video_path>/<int:start_time>/<int:end_time>', methods=['GET'])
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
    # 调用ffmpeg截取视频片段
    output_path = f"{TEMP_PATH}/{start_time}_{end_time}_" + os.path.basename(path)
    if not os.path.exists(output_path):  # 如果存在说明已经剪过，直接返回，如果不存在则剪
        crop_video(path, output_path, start_time, end_time)
    return send_file(output_path)


@app.route('/api/upload', methods=['POST'])
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
    f = request.files['file']
    f.save(temp_path)
    # 计算hash并重命名文件
    new_filename = get_file_hash(temp_path)
    upload_file_path = f"{TEMP_PATH}/{new_filename}"
    os.rename(temp_path, upload_file_path)
    return 'file uploaded successfully'


if __name__ == '__main__':
    init()
    app.run(port=PORT, host=HOST)
