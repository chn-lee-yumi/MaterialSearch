import os
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request, send_file
from database import db, FileType, File
from process_assets import scan_dir, process_image, process_video, process_text, match_image, match_video, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
import pickle
import numpy as np

# TODO：增加反向提示、查询缓存、展示阈值（相似度超过xx分才展示），把top_n改成分页显示？多进程加速搜索？

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

AUTO_SCAN = True
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
    if AUTO_SCAN:
        is_scanning = True
        scan_thread = threading.Thread(target=scan, args=())
        scan_thread.start()


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
    is_scanning = False


def match(text, is_img=False):
    if not is_img:
        text = process_text(text)
    else:
        text = process_image(text)
    scores_list = []
    with app.app_context():
        for file in db.session.query(File):
            features = pickle.loads(file.features)
            if features is None:  # 内容损坏，删除改条记录
                db.session.delete(file)
                db.session.commit()
                continue
            if file.type == FileType.Image:
                score = float(match_image(text, features))
            else:
                score = float(match_video(text, features))
            scores_list.append({"url": "api/get_file/%d" % file.id, "path": file.path, "score": score, "type": file.type})
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
    is_img = data['is_img']
    print(data)
    if is_img:
        sorted_list = match("upload.tmp", is_img=is_img)[:top_n]
    else:
        sorted_list = match(data['text'])[:top_n]
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
