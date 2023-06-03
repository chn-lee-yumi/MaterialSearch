import base64
import datetime
import logging
import os
import pickle
import threading
import time

from flask import Flask, jsonify, request, send_file, abort

from config import *
from database import db, Image, Video, Cache
from process_assets import scan_dir, process_image, process_video, process_text, match_text_and_image, match_batch
from utils import get_file_hash, get_string_hash, softmax

logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assets.db'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True
db.init_app(app)

is_scanning = False
scan_start_time = 0
scanning_files = 0
total_images = 0
total_video_frames = 0
scanned_files = 0
is_continue_scan = False


def init():
    """
    初始化数据库，清缓存，根据AUTO_SCAN决定是否开启自动扫描线程
    :return: None
    """
    global total_images, total_video_frames, is_scanning
    with app.app_context():
        db.create_all()  # 初始化数据库
        total_images = db.session.query(Image).count()  # 获取文件总数
        total_video_frames = db.session.query(Video).count()  # 获取文件总数
    clean_cache()  # 清空搜索缓存
    if AUTO_SCAN:
        auto_scan_thread = threading.Thread(target=auto_scan, args=())
        auto_scan_thread.start()


def clean_cache():
    """
    清空搜索缓存
    :return: None
    """
    with app.app_context():
        db.session.query(Cache).delete()
        db.session.commit()


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
    global is_scanning, total_images, total_video_frames, scanning_files, scanned_files, scan_start_time, is_continue_scan
    logger.info("开始扫描")
    scan_start_time = time.time()
    start_time = time.time()
    if os.path.isfile("assets.pickle"):
        logger.info("读取上次的目录缓存")
        is_continue_scan = True
        with open("assets.pickle", "rb") as f:
            assets = pickle.load(f)
        for asset in assets.copy():
            if asset.startswith(SKIP_PATH):
                assets.remove(asset)
    else:
        is_continue_scan = False
        assets = scan_dir(ASSETS_PATH, SKIP_PATH, IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)
        with open("assets.pickle", "wb") as f:
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
                features = pickle.dumps(features)
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
                    db.session.add(Video(path=asset, frame_time=frame_time, modify_time=modify_time, features=pickle.dumps(features)))
                    total_video_frames = db.session.query(Video).count()  # 获取视频帧总数
            db.session.commit()
            assets.remove(asset)
    scanning_files = 0
    scanned_files = 0
    os.remove("assets.pickle")
    logger.info("扫描完成，用时%d秒" % int(time.time() - start_time))
    clean_cache()  # 清空搜索缓存
    is_scanning = False


def search_image(positive_prompt="", negative_prompt="", img_path="",
                 positive_threshold=POSITIVE_THRESHOLD, negative_threshold=NEGATIVE_THRESHOLD, image_threshold=IMAGE_THRESHOLD):
    """
    搜图
    :param positive_prompt: string, 正向提示词
    :param negative_prompt: string, 反向提示词
    :param img_path: string, 图片路径，如果存在，说明是用图搜索，此时忽略提示词
    :param positive_threshold: int/float, 文字搜索阈值，高于此分数才显示
    :param negative_threshold: int/float, 文字过滤阈值，低于此分数才显示
    :param image_threshold: int/float, 以图搜素材匹配阈值，高于这个分数才展示
    :return:
    """
    if img_path:
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
            features = pickle.loads(file.features)
            if features is None:  # 内容损坏，删除该条记录
                db.session.delete(file)
                db.session.commit()
                continue
            file_list.append(file)
            image_features.append(features)
        scores = match_batch(positive_feature, negative_feature, image_features, positive_threshold, negative_threshold)
        for i in range(len(file_list)):
            if not scores[i]:
                continue
            scores_list.append({"url": "api/get_image/%d" % file_list[i].id, "path": file_list[i].path, "score": float(scores[i])})
    logger.info("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


def search_video(positive_prompt="", negative_prompt="", img_path="",
                 positive_threshold=POSITIVE_THRESHOLD, negative_threshold=NEGATIVE_THRESHOLD, image_threshold=IMAGE_THRESHOLD):
    """
    搜视频
    :param positive_prompt: string, 正向提示词
    :param negative_prompt: string, 反向提示词
    :param img_path: string, 图片路径，如果存在，说明是用图搜索，此时忽略提示词
    :param positive_threshold: int/float, 文字搜索阈值，高于此分数才显示
    :param negative_threshold: int/float, 文字过滤阈值，低于此分数才显示
    :param image_threshold: int/float, 以图搜素材匹配阈值，高于这个分数才展示
    :return:
    """
    if img_path:
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
            image_features = list(map(lambda x: pickle.loads(x.features), frames))
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


@app.route("/", methods=["GET"])
def index_page():
    """主页"""
    return app.send_static_file("index.html")


@app.route("/api/scan", methods=["GET"])
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
    return jsonify({"status": is_scanning, "total_images": total_images, "total_video_frames": total_video_frames, "scanning_files": scanning_files,
                    "remain_files": scanning_files - scanned_files, "progress": progress, "remain_time": int(remain_time),
                    "enable_cache": ENABLE_CACHE})


@app.route("/api/clean_cache", methods=["GET", "POST"])
def api_clean_cache():
    """
    清缓存
    :return: 204 No Content
    """
    clean_cache()
    return "", 204


@app.route("/api/match", methods=["POST"])
def api_match():
    """
    匹配文字对应的素材
    :return:
    """
    data = request.get_json()
    top_n = int(data['top_n'])
    search_type = data['search_type']
    positive_threshold = data['positive_threshold']
    negative_threshold = data['negative_threshold']
    image_threshold = data['image_threshold']
    logger.debug(data)
    # 计算hash
    if search_type == 0:  # 以文搜图
        _hash = get_string_hash(
            "以文搜图%d,%d\npositive: %r\nnegative: %r" % (positive_threshold, negative_threshold, data['positive'], data['negative']))
    elif search_type == 1:  # 以图搜图
        _hash = get_string_hash("以图搜图%d,%s" % (image_threshold, get_file_hash(UPLOAD_TMP_FILE)))
    elif search_type == 2:  # 以文搜视频
        _hash = get_string_hash(
            "以文搜视频%d,%d\npositive: %r\nnegative: %r" % (positive_threshold, negative_threshold, data['positive'], data['negative']))
    elif search_type == 3:  # 以图搜视频
        _hash = get_string_hash("以图搜视频%d,%s" % (image_threshold, get_file_hash(UPLOAD_TMP_FILE)))
    elif search_type == 4:  # 图文比对
        _hash1 = get_string_hash("text: %r" % data['text'])
        _hash2 = get_file_hash(UPLOAD_TMP_FILE)
        _hash = get_string_hash("图文比对\nhash1: %r\nhash2: %r" % (_hash1, _hash2))
    else:
        logger.warning(f"search_type不正确：{search_type}")
        abort(500)
    # 查找cache
    if ENABLE_CACHE:
        if search_type == 0 or search_type == 1 or search_type == 2 or search_type == 3:
            with app.app_context():
                sorted_list = db.session.query(Cache).filter_by(id=_hash).first()
                if sorted_list:
                    sorted_list = pickle.loads(sorted_list.result)
                    logger.debug(f"命中缓存：{_hash}")
                    sorted_list = sorted_list[:top_n]
                    scores = [item["score"] for item in sorted_list]
                    softmax_scores = softmax(scores)
                    if search_type == 0 or search_type == 1:
                        new_sorted_list = [{
                            "url": item["url"], "path": item["path"], "score": "%.2f" % (item["score"] * 100),
                            "softmax_score": "%.2f%%" % (score * 100)
                        } for item, score in zip(sorted_list, softmax_scores)]
                    elif search_type == 2 or search_type == 3:
                        new_sorted_list = [{
                            "url": item["url"], "path": item["path"], "score": "%.2f" % (item["score"] * 100),
                            "softmax_score": "%.2f%%" % (score * 100), "start_time": item["start_time"], "end_time": item["end_time"]
                        } for item, score in zip(sorted_list, softmax_scores)]
                    return jsonify(new_sorted_list)
    # 如果没有cache，进行匹配并写入cache
    if search_type == 0:
        sorted_list = search_image(positive_prompt=data['positive'], negative_prompt=data['negative'],
                                   positive_threshold=positive_threshold, negative_threshold=positive_threshold)[:MAX_RESULT_NUM]
    elif search_type == 1:
        sorted_list = search_image(img_path=UPLOAD_TMP_FILE, image_threshold=image_threshold)[:MAX_RESULT_NUM]
    elif search_type == 2:
        sorted_list = search_video(positive_prompt=data['positive'], negative_prompt=data['negative'],
                                   positive_threshold=positive_threshold, negative_threshold=positive_threshold)[:MAX_RESULT_NUM]
    elif search_type == 3:
        sorted_list = search_video(img_path=UPLOAD_TMP_FILE, image_threshold=image_threshold)[:MAX_RESULT_NUM]
    elif search_type == 4:
        return jsonify({"score": "%.2f" % (match_text_and_image(process_text(data['text']), process_image(UPLOAD_TMP_FILE)) * 100)})
    # 写入缓存
    if ENABLE_CACHE:
        with app.app_context():
            db.session.add(Cache(id=_hash, result=pickle.dumps(sorted_list)))
            db.session.commit()

    sorted_list = sorted_list[:top_n]
    scores = [item["score"] for item in sorted_list]
    softmax_scores = softmax(scores)
    if search_type == 0 or search_type == 1:
        new_sorted_list = [{
            "url": item["url"], "path": item["path"], "score": "%.2f" % (item["score"] * 100), "softmax_score": "%.2f%%" % (score * 100)
        } for item, score in zip(sorted_list, softmax_scores)]
    elif search_type == 2 or search_type == 3:
        new_sorted_list = [{
            "url": item["url"], "path": item["path"], "score": "%.2f" % (item["score"] * 100), "softmax_score": "%.2f%%" % (score * 100),
            "start_time": item["start_time"], "end_time": item["end_time"]
        } for item, score in zip(sorted_list, softmax_scores)]
    return jsonify(new_sorted_list)


@app.route('/api/get_image/<int:image_id>', methods=['GET'])
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


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """上传文件，保存到UPLOAD_TMP_FILE"""
    logger.debug(request.files)
    f = request.files['file']
    f.save(UPLOAD_TMP_FILE)
    return 'file uploaded successfully'


if __name__ == '__main__':
    init()
    app.run(port=PORT, host=HOST)
