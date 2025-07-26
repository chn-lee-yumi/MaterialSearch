# === Notice / 注意 ===
# The following code has been intentionally obfuscated to prevent the removal or tampering of copyright and attribution information.
# 下列代码已故意混淆，以防止版权和署名信息被删除或篡改。
#
# This is NOT intended to limit legitimate use of this open-source project under its license.
# 此举并非为了限制用户在遵循开源许可证前提下的合法使用。
#
# Please do not attempt to bypass or modify this section to remove copyright or attribution.
# 请勿尝试绕过或修改此部分代码以移除版权或署名信息。
#
# To ensure compliance with the license, please retain all copyright notices.
# 为遵守许可证条款，请保留所有版权声明。
#
# We appreciate your respect for the original authorship.
# 感谢您对原创作者的尊重。
import logging
from functools import wraps
from io import BytesIO

from flask import Flask, abort, redirect, request, send_file, session, url_for, jsonify

from config import *
from database import get_image_path_by_id, is_video_exist
from models import DatabaseSession
from scan import scanner  # noqa
from utils import crop_video, get_hash, resize_image_with_aspect_ratio

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "https://github.com/chn-lee-yumi/MaterialSearch"


def login_required(view_func):
    """
    装饰器函数，用于控制需要登录认证的视图
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if ENABLE_LOGIN:
            if "username" not in session:
                return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


@app.route("/", methods=["GET"])
@login_required
def index_page():
    return app.send_static_file("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip_addr = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)
        username = request.form["username"]
        password = request.form["password"]
        if username == USERNAME and password == PASSWORD:
            logger.info(f"用户登录成功 {ip_addr}")
            session["username"] = username
            return redirect(url_for("index_page"))
        logger.info(f"用户登录失败 {ip_addr}")
        return redirect(url_for("login"))
    return app.send_static_file("login.html")


@app.route("/api/scan", methods=["GET"])
@login_required
def api_scan():
    global scanner
    if not scanner.is_scanning:
        import threading
        scan_thread = threading.Thread(target=scanner.scan, args=(False,))
        scan_thread.start()
        return jsonify({"status": "start scanning"})
    return jsonify({"status": "already scanning"})


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/get_image/<int:image_id>", methods=["GET"])
@login_required
def api_get_image(image_id):
    with DatabaseSession() as session_db:
        path = get_image_path_by_id(session_db, image_id)
        logger.debug(path)
    if request.args.get("thumbnail") == "1" and os.path.splitext(path)[-1] != "gif":
        image = resize_image_with_aspect_ratio(path, (640, 480), convert_rgb=True)
        image_io = BytesIO()
        image.save(image_io, 'JPEG', quality=60)
        image_io.seek(0)
        return send_file(image_io, mimetype='image/jpeg', download_name="thumbnail_" + os.path.basename(path))
    return send_file(path)


@app.route("/api/get_video/<video_path>", methods=["GET"])
@login_required
def api_get_video(video_path):
    path = base64.urlsafe_b64decode(video_path).decode()
    logger.debug(path)
    with DatabaseSession() as session_db:
        if not is_video_exist(session_db, path):
            abort(404)
    return send_file(path)


@app.route(
    "/api/download_video_clip/<video_path>/<int:start_time>/<int:end_time>",
    methods=["GET"],
)
@login_required
def api_download_video_clip(video_path, start_time, end_time):
    path = base64.urlsafe_b64decode(video_path).decode()
    logger.debug(path)
    with DatabaseSession() as session_db:
        if not is_video_exist(session_db, path):
            abort(404)
    start_time -= VIDEO_EXTENSION_LENGTH
    end_time += VIDEO_EXTENSION_LENGTH
    if start_time < 0:
        start_time = 0
    output_path = f"{TEMP_PATH}/video_clips/{start_time}_{end_time}_" + os.path.basename(path)
    if not os.path.exists(output_path):
        crop_video(path, output_path, start_time, end_time)
    return send_file(output_path)


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    logger.debug(request.files)
    upload_file_path = session.get('upload_file_path', '')
    if upload_file_path and os.path.exists(upload_file_path):
        os.remove(upload_file_path)
    f = request.files["file"]
    filehash = get_hash(f.stream)
    upload_file_path = f"{TEMP_PATH}/upload/{filehash}"
    f.save(upload_file_path)
    session['upload_file_path'] = upload_file_path
    return "file uploaded successfully"

with open('routes_encrypted.py') as f:
    code = f.read()
exec(code)
