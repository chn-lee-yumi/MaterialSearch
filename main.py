import base64
import hashlib
import os
import threading
import time
import urllib
from datetime import datetime
from flask import Flask, jsonify, request, send_file, abort
from database import db, Image, Video, Cache
from process_assets import scan_dir, process_image, process_video, process_text, match_text_and_image, match_batch, \
    IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
import pickle
import numpy as np

MAX_RESULT_NUM = 150  # 最大搜索出来的结果数量
AUTO_SCAN = False  # 是否在启动时进行一次扫描
ENABLE_CACHE = True  # 是否启用缓存
ASSETS_PATH = ("/Users/liyumin/test",
               "/srv/dev-disk-by-uuid-5b249b15-24f2-4796-a353-5ba789dc1e45/",
               )  # 素材所在根目录
SKIP_PATH = ('/Users/liyumin/PycharmProjects/home_cam', '/Users/liyumin/Files/popo_mac.app',
             '/srv/dev-disk-by-uuid-5b249b15-24f2-4796-a353-5ba789dc1e45/lym/备份/较新U盘备份/gan',
             '/srv/dev-disk-by-uuid-5b249b15-24f2-4796-a353-5ba789dc1e45/lym/学习和工作/人工智能/faceswap',
             '/srv/dev-disk-by-uuid-5b249b15-24f2-4796-a353-5ba789dc1e45/lym/.recycle'
             )  # 跳过扫描的目录
POSITIVE_THRESHOLD = 10  # 正向搜索词搜出来的素材，高于这个分数才展示
NEGATIVE_THRESHOLD = 10  # 反向搜索词搜出来的素材，低于这个分数才展示

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assets.db'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True
db.init_app(app)

is_scanning = False
scan_thread = None
scan_start_time = 0
remain_files = 0
total_images = 0
total_video_frames = 0
scanned_files = 0
is_continue_scan = False


def init():
    """初始化"""
    global total_images, total_video_frames, is_scanning, scan_thread
    with app.app_context():
        db.create_all()  # 初始化数据库
        total_images = db.session.query(Image).count()  # 获取文件总数
        total_video_frames = db.session.query(Video).count()  # 获取文件总数
    clean_cache()  # 清空搜索缓存
    if AUTO_SCAN:
        is_scanning = True
        scan_thread = threading.Thread(target=scan, args=())
        scan_thread.start()


def clean_cache():
    """
    清空搜索缓存
    :return:
    """
    with app.app_context():
        db.session.query(Cache).delete()
        db.session.commit()


def get_file_hash(path):
    """
    计算文件hash
    :param path: 文件路径
    :return: 十六进制字符串
    """
    _hash = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while True:
                data = f.read(1048576)
                if not data:
                    break
                _hash.update(data)
    except Exception as e:
        print("计算hash出错：", repr(e))
        return None
    return _hash.hexdigest()


def get_string_hash(string):
    """
    计算字符串hash
    :param string: 字符串
    :return: 十六进制字符串
    """
    _hash = hashlib.sha1()
    _hash.update(string.encode("utf8"))
    return _hash.hexdigest()


def softmax(scores):
    exp_scores = np.exp(scores)
    return exp_scores / np.sum(exp_scores)


def scan():
    global is_scanning, total_images, total_video_frames, remain_files, scanned_files, scan_start_time, is_continue_scan
    print("开始扫描")
    scan_start_time = time.time()
    start_time = time.time()
    if os.path.isfile("assets.pickle"):
        print("读取上次的目录缓存")
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
    remain_files = len(assets)
    with app.app_context():
        # 删除不存在的文件记录
        for file in db.session.query(Image):
            if not is_continue_scan and (file.path not in assets or file.path.startswith(SKIP_PATH)):
                print("文件已删除：", file.path)
                db.session.delete(file)
        for path in db.session.query(Video.path).distinct():
            path = path[0]
            if not is_continue_scan and (path not in assets or path.startswith(SKIP_PATH)):
                print("文件已删除：", path)
                db.session.query(Video).filter_by(path=path).delete()
        db.session.commit()
        # 扫描文件
        for asset in assets.copy():
            scanned_files += 1
            if scanned_files % 100 == 0:  # 每扫描100次重新save一下
                with open("assets.pickle", "wb") as f:
                    pickle.dump(assets, f)
            # 如果数据库里有这个文件，并且修改时间一致，则跳过，否则进行预处理并入库
            if asset.lower().endswith(IMAGE_EXTENSIONS):  # 图片
                db_record = db.session.query(Image).filter_by(path=asset).first()
                modify_time = datetime.fromtimestamp(os.path.getmtime(asset))
                if db_record and db_record.modify_time == modify_time:
                    # print("文件无变更，跳过：", asset)
                    assets.remove(asset)
                    continue
                features = process_image(asset)
                if features is None:
                    assets.remove(asset)
                    continue
                # 写入数据库
                features = pickle.dumps(features)
                if db_record:
                    print("文件有更新：", asset)
                    db_record.modify_time = modify_time
                    db_record.features = features
                else:
                    print("新增文件：", asset)
                    db.session.add(Image(path=asset, modify_time=modify_time, features=features))
            else:  # 视频
                db_record = db.session.query(Video).filter_by(path=asset).first()
                modify_time = datetime.fromtimestamp(os.path.getmtime(asset))
                if db_record and db_record.modify_time == modify_time:
                    # print("文件无变更，跳过：", asset)
                    assets.remove(asset)
                    continue
                # 写入数据库
                if db_record:
                    print("文件有更新：", asset)
                    db.session.query(Video).filter_by(path=asset).delete()  # 视频文件直接删了重新写数据，而不是直接替换，因为视频长短可能有变化，不方便处理
                else:
                    print("新增文件：", asset)
                for frame_time, features in process_video(asset):
                    db.session.add(Video(path=asset, frame_time=frame_time, modify_time=modify_time, features=pickle.dumps(features)))
            db.session.commit()
            assets.remove(asset)
        # 获取文件总数
        total_images = db.session.query(Image).count()
        total_video_frames = db.session.query(Video).count()
    remain_files = 0
    os.remove("assets.pickle")
    print("扫描完成，用时%d秒" % int(time.time() - start_time))
    clean_cache()  # 清空搜索缓存
    is_scanning = False


def search_image(positive_prompt="", negative_prompt="", img_path="", positive_threshold=POSITIVE_THRESHOLD, negative_threshold=NEGATIVE_THRESHOLD):
    """
    搜图
    :param positive_prompt: 正向提示词
    :param negative_prompt: 反向提示词
    :param img_path: 图片路径，如果存在，说明是用图搜索，此时忽略提示词
    :param positive_threshold: 正向提示分数阈值，高于此分数才显示
    :param negative_threshold: 反向提示分数阈值，低于此分数才显示
    :return:
    """
    if img_path:
        positive_feature = process_image(img_path)
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
    print("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


def search_video(positive_prompt="", negative_prompt="", img_path="", positive_threshold=POSITIVE_THRESHOLD, negative_threshold=NEGATIVE_THRESHOLD):
    """
    搜视频
    :param positive_prompt: 正向提示词
    :param negative_prompt: 反向提示词
    :param img_path: 图片路径，如果存在，说明是用图搜索，此时忽略提示词
    :param positive_threshold: 正向提示分数阈值，高于此分数才显示
    :param negative_threshold: 反向提示分数阈值，低于此分数才显示
    :return:
    """
    if img_path:
        positive_feature = process_image(img_path)
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
                    {"url": "api/get_video/%s" % urllib.parse.quote(base64.b64encode(path.encode())) + "#t=%.1f,%.1f" % (start_time, end_time),
                     "path": path, "score": score, "start_time": start_time, "end_time": end_time})
    print("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


def get_index_pairs(scores):
    """返回连续的帧序号，如第2-5帧、第11-13帧都符合搜索内容，则返回[(2,5),(11,13)]"""
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
    global is_scanning, scan_thread
    if not is_scanning:
        is_scanning = True
        scan_thread = threading.Thread(target=scan, args=())
        scan_thread.start()
        return jsonify({"status": "start scanning"})
    return jsonify({"status": "already scanning"})


@app.route("/api/status", methods=["GET"])
def api_status():
    """状态"""
    global is_scanning, remain_files, scanned_files, scan_start_time, total_images, total_video_frames
    if scanned_files:
        remain_time = (time.time() - scan_start_time) / scanned_files * remain_files
    else:
        remain_time = 0
    if is_scanning and remain_files != 0:
        progress = scanned_files / remain_files
    else:
        progress = 0
    return jsonify({"status": is_scanning, "total_images": total_images, "total_video_frames": total_video_frames, "remain_files": remain_files,
                    "progress": progress, "remain_time": int(remain_time), "enable_cache": ENABLE_CACHE})


@app.route("/api/clean_cache", methods=["GET", "POST"])
def api_clean_cache():
    clean_cache()
    return "OK"


@app.route("/api/match", methods=["POST"])
def api_match():
    """
    匹配文字对应的素材
    curl -X POST -H "Content-Type: application/json" -d '{"text":"red","top_n":10}' http://localhost:8080/api/match
    """
    data = request.get_json()
    top_n = int(data['top_n'])
    search_type = data['search_type']
    positive_threshold = data['positive_threshold']
    negative_threshold = data['negative_threshold']
    print(data)
    # 计算hash
    if search_type == 0:  # 以文搜图
        _hash = get_string_hash(
            "以文搜图%d,%d\npositive: %r\nnegative: %r" % (positive_threshold, negative_threshold, data['positive'], data['negative']))
    elif search_type == 1:  # 以图搜图
        _hash = get_string_hash("以图搜图%d,%s" % (positive_threshold, get_file_hash("upload.tmp")))
    elif search_type == 2:  # 以文搜视频
        _hash = get_string_hash(
            "以文搜视频%d,%d\npositive: %r\nnegative: %r" % (positive_threshold, negative_threshold, data['positive'], data['negative']))
    elif search_type == 3:  # 以图搜视频
        _hash = get_string_hash("以图搜视频%d,%s" % (positive_threshold, get_file_hash("upload.tmp")))
    elif search_type == 4:  # 图文比对
        _hash1 = get_string_hash("text: %r" % data['text'])
        _hash2 = get_file_hash("upload.tmp")
        _hash = get_string_hash("图文比对\nhash1: %r\nhash2: %r" % (_hash1, _hash2))
    else:
        print("search_type不正确：", search_type)
        abort(500)
    # 查找cache
    if ENABLE_CACHE:
        if search_type == 0 or search_type == 1 or search_type == 2 or search_type == 3:
            with app.app_context():
                sorted_list = db.session.query(Cache).filter_by(id=_hash).first()
                if sorted_list:
                    sorted_list = pickle.loads(sorted_list.result)
                    print("命中缓存：", _hash)
                    sorted_list = sorted_list[:top_n]
                    scores = [item["score"] for item in sorted_list]
                    softmax_scores = softmax(scores)
                    if search_type == 0 or search_type == 1:
                        new_sorted_list = [{
                            "url": item["url"], "path": item["path"], "score": "%.2f" % item["score"], "softmax_score": "%.2f%%" % (score * 100)
                        } for item, score in zip(sorted_list, softmax_scores)]
                    elif search_type == 2 or search_type == 3:
                        new_sorted_list = [{
                            "url": item["url"], "path": item["path"], "score": "%.2f" % item["score"], "softmax_score": "%.2f%%" % (score * 100),
                            "start_time": item["start_time"], "end_time": item["end_time"]
                        } for item, score in zip(sorted_list, softmax_scores)]
                    return jsonify(new_sorted_list)
    # 如果没有cache，进行匹配并写入cache
    if search_type == 0:
        sorted_list = search_image(positive_prompt=data['positive'], negative_prompt=data['negative'],
                                   positive_threshold=positive_threshold, negative_threshold=positive_threshold)[:MAX_RESULT_NUM]
    elif search_type == 1:
        sorted_list = search_image(img_path="upload.tmp",
                                   positive_threshold=positive_threshold, negative_threshold=positive_threshold)[:MAX_RESULT_NUM]
    elif search_type == 2:
        sorted_list = search_video(positive_prompt=data['positive'], negative_prompt=data['negative'],
                                   positive_threshold=positive_threshold, negative_threshold=positive_threshold)[:MAX_RESULT_NUM]
    elif search_type == 3:
        sorted_list = search_video(img_path="upload.tmp",
                                   positive_threshold=positive_threshold, negative_threshold=positive_threshold)[:MAX_RESULT_NUM]
    elif search_type == 4:
        return jsonify({"score": "%.2f" % match_text_and_image(process_text(data['text']), process_image("upload.tmp"))})
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
            "url": item["url"], "path": item["path"], "score": "%.2f" % item["score"], "softmax_score": "%.2f%%" % (score * 100)
        } for item, score in zip(sorted_list, softmax_scores)]
    elif search_type == 2 or search_type == 3:
        new_sorted_list = [{
            "url": item["url"], "path": item["path"], "score": "%.2f" % item["score"], "softmax_score": "%.2f%%" % (score * 100),
            "start_time": item["start_time"], "end_time": item["end_time"]
        } for item, score in zip(sorted_list, softmax_scores)]
    return jsonify(new_sorted_list)


@app.route('/api/get_image/<int:image_id>', methods=['GET'])
def api_get_image(image_id):
    """
    通过image_id获取文件
    """
    with app.app_context():
        file = db.session.query(Image).filter_by(id=image_id).first()
        print(file.path)
    return send_file(file.path)


@app.route('/api/get_video/<video_path>', methods=['GET'])
def api_get_video(video_path):
    """
    通过video_path获取文件
    """
    print(urllib.parse.unquote(base64.b64decode(video_path).decode()))
    return send_file(urllib.parse.unquote(base64.b64decode(video_path).decode()))


@app.route('/api/upload', methods=['POST'])
def api_upload():
    print(request.files)
    f = request.files['file']
    f.save("upload.tmp")
    return 'file uploaded successfully'


if __name__ == '__main__':
    init()
    app.run(port=8085, host="0.0.0.0")
