import hashlib
import os
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request, send_file, abort
from database import db, FileType, File, Cache
from process_assets import scan_dir, process_image, process_video, process_text, match_image, match_video, match_batch, \
    IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
import pickle
import numpy as np

# TODO: 视频另外分个表？视频改为每采样帧一行记录？定位出查询内容所在视频时间。
# TODO: 增加图文相似度匹配计算功能

MAX_RESULT_NUM = 150  # 最大搜索出来的结果数量
AUTO_SCAN = False  # 是否在启动时进行一次扫描
ENABLE_CACHE = True  # 是否启用缓存
ASSETS_PATH = ("/Users/liyumin/",
               "/srv/dev-disk-by-uuid-5b249b15-24f2-4796-a353-5ba789dc1e45/",
               )  # 素材所在根目录
SKIP_PATH = ('/Users/liyumin/PycharmProjects/home_cam', '/Users/liyumin/Files/popo_mac.app',
             '/srv/dev-disk-by-uuid-5b249b15-24f2-4796-a353-5ba789dc1e45/lym/备份/较新U盘备份/gan',
             '/srv/dev-disk-by-uuid-5b249b15-24f2-4796-a353-5ba789dc1e45/lym/学习和工作/人工智能/faceswap',
             '/srv/dev-disk-by-uuid-5b249b15-24f2-4796-a353-5ba789dc1e45/lym/.recycle'
             )  # 跳过扫描的目录

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assets.db'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True
db.init_app(app)

is_scanning = False
scan_thread = None
scan_start_time = 0
total_files = 0
scanned_files = 0
is_continue_scan = False


def init():
    """初始化"""
    global total_files, is_scanning, scan_thread
    with app.app_context():
        db.create_all()  # 初始化数据库
        total_files = db.session.query(File).count()  # 获取文件总数
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
    global is_scanning, total_files, scanned_files, scan_start_time, is_continue_scan
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
    total_files = len(assets)
    with app.app_context():
        # 删除不存在的文件记录
        for file in db.session.query(File):
            if not is_continue_scan and (file.path not in assets or file.path.startswith(SKIP_PATH)):
                print("文件已删除：", file.path)
                db_record = db.session.query(File).filter_by(path=file.path).first()
                db.session.delete(db_record)
        db.session.commit()
        # 扫描文件
        for asset in assets.copy():
            scanned_files += 1
            if scanned_files % 50 == 0:  # 每扫描50次重新save一下
                with open("assets.pickle", "wb") as f:
                    pickle.dump(assets, f)
            # 如果数据库里有这个文件，并且修改时间一致，则跳过，否则进行预处理并入库
            db_record = db.session.query(File).filter_by(path=asset).first()
            modify_time = datetime.fromtimestamp(os.path.getmtime(asset))
            if db_record and db_record.modify_time == modify_time:
                # print("文件无变更，跳过：", asset)
                assets.remove(asset)
                continue
            # 判断文件类型并获取feature
            if asset.lower().endswith(IMAGE_EXTENSIONS):  # 属于图片
                file_type = FileType.Image
                features = process_image(asset)
                if features is None:
                    assets.remove(asset)
                    continue
            else:  # 属于视频
                file_type = FileType.Video
                features = process_video(asset)
                if features is None:
                    assets.remove(asset)
                    continue
            # 写入
            if db_record:
                print("文件有更新：", asset)
                features = pickle.dumps(features)
                db_record.modify_time = modify_time
                db_record.features = features
            else:
                print("新增文件：", asset)
                features = pickle.dumps(features)
                db.session.add(File(type=file_type, path=asset, modify_time=modify_time, features=features))
            db.session.commit()
            assets.remove(asset)
        total_files = db.session.query(File).count()  # 获取文件总数
    os.remove("assets.pickle")
    print("扫描完成，用时%d秒" % int(time.time() - start_time))
    clean_cache()  # 清空搜索缓存
    is_scanning = False


def match(positive="", negative="", img_path=""):
    if img_path:
        text_positive = process_image(img_path)
    else:
        text_positive = process_text(positive)
    if negative:
        text_negative = process_text(negative)
    else:
        text_negative = None
    scores_list = []
    t0 = time.time()
    with app.app_context():
        # 查询图片
        batch = []
        file_list = []
        for file in db.session.query(File).filter_by(type=FileType.Image):
            features = pickle.loads(file.features)
            if features is None:  # 内容损坏，删除该条记录
                db.session.delete(file)
                db.session.commit()
                continue
            file_list.append(file)
            batch.append(features)
        scores = match_batch(text_positive, text_negative, batch)
        for i in range(len(file_list)):
            if not scores[i]:
                continue
            scores_list.append(
                {"url": "api/get_file/%d" % file_list[i].id, "path": file_list[i].path, "score": float(scores[i]), "type": file_list[i].type})
        # 查询视频
        for file in db.session.query(File).filter_by(type=FileType.Video):
            features = pickle.loads(file.features)
            if features is None:  # 内容损坏，删除该条记录
                db.session.delete(file)
                db.session.commit()
                continue
            score = match_video(text_positive, text_negative, features)
            if score is None:
                continue
            scores_list.append({"url": "api/get_file/%d" % file.id, "path": file.path, "score": float(score), "type": file.type})
    print("查询使用时间：%.2f" % (time.time() - t0))
    sorted_list = sorted(scores_list, key=lambda x: x["score"], reverse=True)
    return sorted_list


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


@app.route("/api/scan_status", methods=["GET"])
def api_scan_status():
    """扫描状态"""
    global is_scanning, total_files, scanned_files, scan_start_time
    remain_files = total_files - scanned_files
    if scanned_files:
        remain_time = (time.time() - scan_start_time) / scanned_files * remain_files
    else:
        remain_time = 0
    if is_scanning and total_files != 0:
        progress = scanned_files / total_files
    else:
        progress = 0
    return jsonify({"status": is_scanning, "total": total_files, "remain_files": remain_files,
                    "progress": progress,
                    "remain_time": int(remain_time)})


@app.route("/api/match", methods=["POST"])
def api_match():
    """
    匹配文字对应的素材
    curl -X POST -H "Content-Type: application/json" -d '{"text":"red","top_n":10}' http://localhost:8080/api/match
    """
    data = request.get_json()
    top_n = int(data['top_n'])
    search_type = data['search_type']
    print(data)
    # 计算hash
    if search_type == 0:
        _hash = get_string_hash("positive: %r\nnegative: %r" % (data['positive'], data['negative']))
    elif search_type == 1:
        _hash = get_file_hash("upload.tmp")
    elif search_type == 2:
        _hash1 = get_string_hash("text: %r" % data['text'])
        _hash2 = get_file_hash("upload.tmp")
        _hash = get_string_hash("hash1: %r\nhash2: %r" % (_hash1, _hash2))
    else:
        abort(500)
    if not _hash:
        abort(500)
    # 查找cache
    if ENABLE_CACHE:
        if search_type == 0 or search_type == 1:
            with app.app_context():
                sorted_list = db.session.query(Cache).filter_by(id=_hash).first()
                if sorted_list:
                    sorted_list = pickle.loads(sorted_list.result)
                    print("命中缓存：", _hash)
                    sorted_list = sorted_list[:top_n]
                    scores = [item["score"] for item in sorted_list]
                    softmax_scores = softmax(scores)
                    new_sorted_list = [{
                        "url": item["url"], "path": item["path"], "score": "%.2f" % item["score"], "softmax_score": "%.2f%%" % (score * 100),
                        "type": item["type"]
                    } for item, score in zip(sorted_list, softmax_scores)]
                    return jsonify(new_sorted_list)
    # 如果没有cache，进行匹配并写入cache
    if search_type == 0:
        sorted_list = match(positive=data['positive'], negative=data['negative'])[:MAX_RESULT_NUM]
    elif search_type == 1:
        sorted_list = match(img_path="upload.tmp")[:MAX_RESULT_NUM]
    elif search_type == 2:
        return jsonify({"score": "%.2f" % match_image(process_text(data['text']), process_image("upload.tmp"))})
    # 写入缓存
    if ENABLE_CACHE:
        with app.app_context():
            db.session.add(Cache(id=_hash, result=pickle.dumps(sorted_list)))
            db.session.commit()
    sorted_list = sorted_list[:top_n]
    scores = [item["score"] for item in sorted_list]
    softmax_scores = softmax(scores)
    new_sorted_list = [{
        "url": item["url"], "path": item["path"], "score": "%.2f" % item["score"], "softmax_score": "%.2f%%" % (score * 100), "type": item["type"]
    } for item, score in zip(sorted_list, softmax_scores)]
    return jsonify(new_sorted_list)


@app.route('/api/get_file/<int:file_id>', methods=['GET'])
def api_get_file(file_id):
    """
    通过file_id获取文件
    """
    with app.app_context():
        file = db.session.query(File).filter_by(id=file_id).first()
        print(file.path)
    return send_file(file.path)


@app.route('/api/upload', methods=['POST'])
def api_upload():
    print(request.files)
    f = request.files['file']
    f.save("upload.tmp")
    return 'file uploaded successfully'


if __name__ == '__main__':
    init()
    app.run(port=8085, host="0.0.0.0")
