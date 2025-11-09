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
import base64
import datetime
import hashlib
import logging
import os
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from functools import wraps
from io import BytesIO
from pathlib import PureWindowsPath
from urllib.parse import quote, unquote

from flask import Flask, abort, redirect, request, send_file, session, url_for, jsonify
from PIL import Image as PILImage

from config import *
from database import get_image_path_by_id, is_video_exist, get_db_manager, add_image, add_video
from models import DatabaseSession, Image
from process_assets import match_text_and_image, process_image, process_text, process_images, process_video
from scan import scanner  # noqa
from utils import get_file_hash
from utils_image import calculate_image_properties
from search import (
    search_image_by_image,
    search_image_by_text_path_time,
    search_video_by_image,
    search_video_by_text_path_time,
    search_pexels_video_by_text,
)
from utils import crop_video, get_hash, resize_image_with_aspect_ratio
from project_manager import get_project_manager
from archive import get_archive_manager

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "https://github.com/chn-lee-yumi/MaterialSearch"

# 批量索引任务字典 (task_id -> task_info)
indexing_tasks = {}
indexing_task_events = {}
indexing_task_decisions = {}

THUMBNAIL_CACHE_DIR = os.path.join(TEMP_PATH, 'thumbnails')
THUMBNAIL_CACHE_TTL = 7 * 24 * 3600
THUMBNAIL_LARGE_FILE_THRESHOLD = 100 * 1024 * 1024
THUMBNAIL_TIMEOUT_SECONDS = 5
TASK_RETENTION_SECONDS = 24 * 3600
MAX_DUPLICATE_WAIT_SECONDS = 300

thumbnail_cache_last_cleanup = 0
default_thumbnail_bytes = {}


def cleanup_indexing_tasks():
    """清理已完成且超时的索引任务，避免占用内存。"""
    now = time.time()
    expired = []
    for task_id, task in list(indexing_tasks.items()):
        status = task.get('status')
        updated_at = task.get('updated_at', task.get('start_time', now))
        if status in ('completed', 'failed', 'cancelled') and now - updated_at > TASK_RETENTION_SECONDS:
            expired.append(task_id)
    for task_id in expired:
        indexing_tasks.pop(task_id, None)
        indexing_task_events.pop(task_id, None)
        indexing_task_decisions.pop(task_id, None)


def apply_path_mappings(path: str) -> str:
    """根据 PATH_MAPPINGS 将盘符映射到真实 UNC 路径。"""
    if not PATH_MAPPINGS:
        return path
    normalized = str(PureWindowsPath(path))
    normalized_upper = normalized.upper()
    for mapping in PATH_MAPPINGS:
        prefix = mapping['source_std']
        if not prefix.endswith('\\'):
            prefix = f"{prefix}\\"
        if normalized_upper.startswith(prefix):
            base = mapping['source_norm']
            if not base.endswith('\\'):
                base = f"{base}\\"
            remainder = normalized[len(base):].lstrip('\\/')
            target = mapping['target'].rstrip('\\/')
            return target if not remainder else f"{target}\\{remainder}"
    return normalized


def normalize_input_path(raw_path: str) -> str:
    """清理输入并统一为系统可访问的绝对路径。"""
    path = (raw_path or '').strip().strip('"').strip("'")
    if not path:
        raise ValueError("路径不能为空")
    try:
        windows_path = PureWindowsPath(path)
    except Exception:
        raise ValueError(f"路径格式不受支持: {raw_path}")
    if not windows_path.is_absolute():
        raise ValueError(f"不支持相对路径: {raw_path}")
    normalized = str(windows_path)
    normalized = apply_path_mappings(normalized)
    return os.path.normpath(normalized)


def cleanup_thumbnail_cache(cache_dir: str):
    """定期清理缩略图缓存目录，移除 7 天前的文件。"""
    global thumbnail_cache_last_cleanup
    now = time.time()
    if now - thumbnail_cache_last_cleanup < 3600:
        return
    if not os.path.isdir(cache_dir):
        return
    for filename in os.listdir(cache_dir):
        file_path = os.path.join(cache_dir, filename)
        try:
            if os.path.isfile(file_path):
                age = now - os.path.getmtime(file_path)
                if age > THUMBNAIL_CACHE_TTL:
                    os.remove(file_path)
        except Exception as e:
            logger.warning(f"清理缩略图缓存失败: {file_path} - {e}")
    thumbnail_cache_last_cleanup = now


def serve_default_thumbnail(size: int):
    """返回内置的占位缩略图。"""
    if size not in default_thumbnail_bytes:
        placeholder = PILImage.new('RGB', (size, size), color=(245, 247, 250))
        buffer = BytesIO()
        placeholder.save(buffer, 'JPEG', quality=70)
        default_thumbnail_bytes[size] = buffer.getvalue()
    return send_file(BytesIO(default_thumbnail_bytes[size]), mimetype='image/jpeg')


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


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


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


@app.route("/api/match", methods=["POST"])
@login_required
def api_match():
    data = request.get_json()
    top_n = int(data["top_n"])
    search_type = data["search_type"]
    positive_threshold = data["positive_threshold"]
    negative_threshold = data["negative_threshold"]
    image_threshold = data["image_threshold"]
    img_id = data["img_id"]
    path = data["path"]
    start_time = data["start_time"]
    end_time = data["end_time"]
    # 新增库类型参数
    library_type = data.get("library_type", "permanent")
    project_id = data.get("project_id")

    if library_type not in {"permanent", "project"}:
        return jsonify({"error": "library_type 仅支持 'permanent' 或 'project'"}), 400

    if library_type == "project":
        if not project_id:
            return jsonify({"error": "library_type='project' 时必须提供 project_id"}), 400
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if not project:
            return jsonify({"error": f"项目不存在: {project_id}"}), 404

    upload_file_path = session.get('upload_file_path', '')
    session['upload_file_path'] = ""
    if search_type in (1, 3, 4):
        if not upload_file_path or not os.path.exists(upload_file_path):
            return "你没有上传文件！", 400
    logger.debug(data)
    if search_type == 0:
        results = search_image_by_text_path_time(data["positive"], data["negative"], positive_threshold, negative_threshold,
                                                 path, start_time, end_time, library_type, project_id)
    elif search_type == 1:
        results = search_image_by_image(upload_file_path, image_threshold, path, start_time, end_time, library_type, project_id)
    elif search_type == 2:
        results = search_video_by_text_path_time(data["positive"], data["negative"], positive_threshold, negative_threshold,
                                                 path, start_time, end_time, library_type, project_id)
    elif search_type == 3:
        results = search_video_by_image(upload_file_path, image_threshold, path, start_time, end_time, library_type, project_id)
    elif search_type == 4:
        score = match_text_and_image(process_text(data["positive"]), process_image(upload_file_path)) * 100
        return jsonify({"score": "%.2f" % score})
    elif search_type == 5:
        results = search_image_by_image(img_id, image_threshold, path, start_time, end_time, library_type, project_id)
    elif search_type == 6:
        results = search_video_by_image(img_id, image_threshold, path, start_time, end_time, library_type, project_id)
    elif search_type == 9:
        results = search_pexels_video_by_text(data["positive"], positive_threshold)
    else:
        logger.warning(f"search_type不正确：{search_type}")
        abort(400)
    return jsonify(results[:top_n])


# ============================================
# 项目管理 API
# ============================================

@app.route("/api/projects", methods=["GET", "POST"])
@login_required
def api_projects():
    """获取项目列表或创建新项目"""
    pm = get_project_manager()

    if request.method == "GET":
        # 获取项目列表
        status = request.args.get("status")
        include_deleted = request.args.get("include_deleted", "false").lower() == "true"

        try:
            projects = pm.list_projects(status=status, include_deleted=include_deleted)
            return jsonify({
                "success": True,
                "data": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "client_name": p.client_name,
                        "description": p.description,
                        "status": p.status,
                        "image_count": p.image_count,
                        "video_count": p.video_count,
                        "total_size": p.total_size,
                        "created_time": p.created_time.isoformat() if p.created_time else None,
                        "updated_time": p.updated_time.isoformat() if p.updated_time else None,
                    }
                    for p in projects
                ]
            })
        except Exception as e:
            logger.error(f"获取项目列表失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    elif request.method == "POST":
        # 创建新项目
        data = request.get_json()
        name = data.get("name")
        client_name = data.get("client_name")
        description = data.get("description")

        if not name:
            return jsonify({"success": False, "error": "项目名称不能为空"}), 400

        try:
            project = pm.create_project(
                name=name,
                client_name=client_name,
                description=description
            )
            return jsonify({
                "success": True,
                "data": {
                    "id": project.id,
                    "name": project.name,
                    "client_name": project.client_name,
                    "description": project.description,
                    "status": project.status,
                    "created_time": project.created_time.isoformat() if project.created_time else None,
                }
            })
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            logger.error(f"创建项目失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<project_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_project_detail(project_id):
    """获取、更新或删除项目"""
    pm = get_project_manager()

    if request.method == "GET":
        # 获取项目详情
        try:
            project = pm.get_project(project_id)
            if not project:
                return jsonify({"success": False, "error": "项目不存在"}), 404

            return jsonify({
                "success": True,
                "data": {
                    "id": project.id,
                    "name": project.name,
                    "client_name": project.client_name,
                    "description": project.description,
                    "status": project.status,
                    "image_count": project.image_count,
                    "video_count": project.video_count,
                    "total_size": project.total_size,
                    "created_time": project.created_time.isoformat() if project.created_time else None,
                    "updated_time": project.updated_time.isoformat() if project.updated_time else None,
                }
            })
        except Exception as e:
            logger.error(f"获取项目详情失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    elif request.method == "PUT":
        # 更新项目
        data = request.get_json()
        try:
            project = pm.update_project(
                project_id=project_id,
                name=data.get("name"),
                client_name=data.get("client_name"),
                description=data.get("description"),
                status=data.get("status")
            )
            return jsonify({
                "success": True,
                "data": {
                    "id": project.id,
                    "name": project.name,
                    "client_name": project.client_name,
                    "description": project.description,
                    "status": project.status,
                    "updated_time": project.updated_time.isoformat() if project.updated_time else None,
                }
            })
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            logger.error(f"更新项目失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    elif request.method == "DELETE":
        # 删除项目
        hard_delete = request.args.get("hard_delete", "false").lower() == "true"
        try:
            pm.delete_project(project_id, hard_delete=hard_delete)
            return jsonify({"success": True, "message": "项目已删除"})
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 404
        except Exception as e:
            logger.error(f"删除项目失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<project_id>/stats", methods=["GET"])
@login_required
def api_project_stats(project_id):
    """获取项目统计信息"""
    pm = get_project_manager()

    try:
        stats = pm.get_project_stats(project_id)
        return jsonify({"success": True, "data": stats})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error(f"获取项目统计失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<project_id>/update_stats", methods=["POST"])
@login_required
def api_project_update_stats(project_id):
    """更新项目统计信息"""
    pm = get_project_manager()

    try:
        pm.update_project_stats(project_id)
        return jsonify({"success": True, "message": "统计信息已更新"})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error(f"更新项目统计失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================
# 归档功能 API
# ============================================

@app.route("/api/projects/<project_id>/archive", methods=["POST"])
@login_required
def api_archive_images(project_id):
    """归档项目图片到永久库"""
    am = get_archive_manager()

    data = request.get_json()
    image_ids = data.get("image_ids", [])
    mark_archived = data.get("mark_archived", True)

    if not image_ids:
        return jsonify({"success": False, "error": "未指定要归档的图片"}), 400

    try:
        result = am.archive_images_to_permanent(
            project_id=project_id,
            image_ids=image_ids,
            mark_archived=mark_archived
        )
        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as e:
        logger.error(f"归档失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<project_id>/archived", methods=["GET"])
@login_required
def api_get_archived_images(project_id):
    """获取项目中已归档的图片列表"""
    am = get_archive_manager()

    try:
        archived_images = am.get_archived_images(project_id)
        return jsonify({
            "success": True,
            "data": archived_images
        })
    except Exception as e:
        logger.error(f"获取归档列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<project_id>/unarchive", methods=["POST"])
@login_required
def api_unarchive_images(project_id):
    """取消归档标记"""
    am = get_archive_manager()

    data = request.get_json()
    image_ids = data.get("image_ids", [])

    if not image_ids:
        return jsonify({"success": False, "error": "未指定要取消归档的图片"}), 400

    try:
        result = am.unarchive_images(project_id, image_ids)
        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as e:
        logger.error(f"取消归档失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 库类型选择功能集成（必须在加密路由之前定义）==========

@app.route("/api/scan", methods=["GET"])
@login_required
def api_scan_new():
    """
    扫描API - 支持目标库选择
    查询参数:
        target (str): 目标库，'permanent' 或 'proj_xxx'，默认 'permanent'
        path (str): 自定义扫描路径（可指定多个，如 path=/path/1&path=/path/2）
    """
    target = request.args.get('target', 'permanent')
    logger.info(f"接收到扫描请求: target={target}")

    # 获取自定义扫描路径（支持多个path参数）
    scan_paths = request.args.getlist('path')
    # 如果指定路径且目标是项目库，则使用自定义路径
    # 如果目标是永久库，仍然使用环境变量配置（保持永久库的固定性）
    if scan_paths and target != 'permanent':
        logger.info(f"使用自定义扫描路径: {scan_paths}")
    elif target != 'permanent':
        # 项目库但未指定路径，返回错误（避免意外扫描到永久库路径）
        return jsonify({
            "success": False,
            "error": "项目库扫描必须指定路径参数（path）"
        }), 400

    # 验证项目是否存在（如果目标是项目库）
    if target.startswith('proj_'):
        try:
            pm = get_project_manager()
            project = pm.get_project(target)
            if not project:
                return jsonify({"success": False, "error": f"项目不存在: {target}"}), 404
        except Exception as e:
            logger.error(f"验证项目失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # 检查是否正在扫描
    if scanner.is_scanning:
        return jsonify({"success": False, "error": "扫描进行中，请稍后再试"}), 409

    # 启动扫描（在新线程中）
    import threading
    try:
        # 传递 scan_paths 参数（如果是项目库）
        if target != 'permanent':
            logger.info(f"准备扫描项目库: target={target}, paths={scan_paths}")
            scan_thread = threading.Thread(
                target=scanner.scan,
                args=(False, target, scan_paths)
            )
        else:
            scan_thread = threading.Thread(
                target=scanner.scan,
                args=(False, target)
            )
        scan_thread.start()
        message = f"开始扫描到 {target}"
        if scan_paths:
            message += f" (路径: {', '.join(scan_paths[:2])}{'...' if len(scan_paths) > 2 else ''})"
        return jsonify({"success": True, "message": message})
    except Exception as e:
        logger.error(f"启动扫描失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/status", methods=["GET"])
@login_required
def api_status():
    """
    获取扫描状态 - 覆盖原有版本
    """
    return jsonify(scanner.get_status())


# 覆盖资源接口以支持项目库
@app.route("/api/get_image/<int:image_id>", methods=["GET"])
@login_required
def api_get_image_with_target(image_id):
    """
    获取图片 - 支持指定库
    查询参数:
        target (str): 'permanent' 或 'proj_xxx'，默认 'permanent'
    """
    target = request.args.get('target', 'permanent')

    # 获取正确的 session
    if target == 'permanent':
        session = get_db_manager().get_permanent_session()
    elif target.startswith('proj_'):
        session = get_db_manager().get_project_session(target)
    else:
        session = DatabaseSession()

    with session:
        image = session.query(Image).filter(Image.id == image_id).first()
        if not image:
            abort(404)

        # 检查是否请求缩略图
        if request.args.get('thumbnail'):
            # 动态生成缩略图
            img = resize_image_with_aspect_ratio(image.path, (640, 480), convert_rgb=True)
            img_io = BytesIO()
            img.save(img_io, 'JPEG', quality=60)
            img_io.seek(0)
            return send_file(img_io, mimetype='image/jpeg')
        else:
            return send_file(image.path)


@app.route("/api/get_video/<path:video_path>", methods=["GET"])
@login_required
def api_get_video_with_target(video_path):
    """
    获取视频 - 暂时保持原有逻辑（视频路径不包含 ID，难以路由到项目库）
    TODO: 未来可能需要改进视频的项目库支持
    """
    video_path = base64.urlsafe_b64decode(video_path).decode()
    return send_file(video_path)


# ========== 批量上传功能 ==========

@app.route("/api/preview_files", methods=["POST"])
@login_required
def api_preview_files():
    """
    路径预览 API - 接收路径列表,返回文件元信息
    """
    try:
        data = request.json or {}
        if 'paths' not in data:
            return jsonify({"error": "缺少 paths 参数"}), 400

        paths = data.get('paths')
        target = data.get('target', 'permanent')

        if not isinstance(paths, list) or len(paths) == 0:
            return jsonify({"error": "paths 必须是非空数组"}), 400

        logger.info(f"路径预览请求: {len(paths)} 个路径, target={target}")

        if target == 'permanent':
            db_session = get_db_manager().get_permanent_session()
        elif target.startswith('proj_'):
            db_session = get_db_manager().get_project_session(target)
        else:
            return jsonify({"error": f"无效的目标库: {target}"}), 400

        normalized_inputs = []
        seen_inputs = set()
        for raw_path in paths:
            try:
                normalized = normalize_input_path(raw_path)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            key = normalized.lower()
            if key in seen_inputs:
                continue
            seen_inputs.add(key)
            normalized_inputs.append(normalized)

        if not normalized_inputs:
            return jsonify({"error": "未提供有效路径"}), 400

        for candidate in normalized_inputs:
            if not os.path.exists(candidate):
                return jsonify({"error": f"路径不存在: {candidate}"}), 400

        temp_patterns = ['~$', '.DS_Store', 'Thumbs.db', '.tmp', '.temp', 'desktop.ini']

        def is_temp_file(filename: str) -> bool:
            lower_name = filename.lower()
            return any(pattern.lower() in lower_name for pattern in temp_patterns)

        def is_supported_file(filepath: str) -> bool:
            ext = os.path.splitext(filepath)[1].lower()
            return ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS

        result = []
        visited_files = set()

        with db_session as session:
            def get_file_metadata(filepath: str):
                try:
                    filename = os.path.basename(filepath)
                    if is_temp_file(filename):
                        return None

                    ext = os.path.splitext(filepath)[1].lower()
                    if ext in IMAGE_EXTENSIONS:
                        file_type = 'image'
                    elif ext in VIDEO_EXTENSIONS:
                        file_type = 'video'
                    else:
                        return None

                    file_size = os.path.getsize(filepath)
                    mtime = int(os.path.getmtime(filepath))

                    existing = session.query(Image).filter(Image.path == filepath).first()

                    return {
                        'path': filepath,
                        'filename': filename,
                        'size': file_size,
                        'type': file_type,
                        'ext': ext,
                        'mtime': mtime,
                        'is_indexed': existing is not None,
                        'phash': existing.phash if existing else None
                    }
                except Exception as err:
                    logger.warning(f"获取文件元信息失败 {filepath}: {err}")
                    return None

            for root_path in normalized_inputs:
                if os.path.isfile(root_path):
                    if not is_supported_file(root_path):
                        continue
                    metadata = get_file_metadata(root_path)
                    if metadata:
                        key = metadata['path'].lower()
                        if key not in visited_files:
                            visited_files.add(key)
                            result.append(metadata)
                elif os.path.isdir(root_path):
                    try:
                        for walk_root, dirs, files in os.walk(root_path):
                            dirs[:] = [d for d in dirs if not d.startswith('.')]
                            for filename in files:
                                if filename.startswith('.'):
                                    continue
                                full_path = os.path.join(walk_root, filename)
                                if not is_supported_file(full_path):
                                    continue
                                metadata = get_file_metadata(full_path)
                                if metadata:
                                    key = metadata['path'].lower()
                                    if key in visited_files:
                                        continue
                                    visited_files.add(key)
                                    result.append(metadata)
                    except PermissionError as perm_err:
                        logger.error(f"访问路径权限不足: {root_path} - {perm_err}")
                        return jsonify({"error": f"路径访问权限不足: {root_path}"}), 400
                else:
                    return jsonify({"error": f"路径不可用: {root_path}"}), 400

        logger.info(f"路径预览完成: 找到 {len(result)} 个文件")
        return jsonify(result)

    except PermissionError as e:
        logger.error(f"路径访问权限不足: {e}")
        return jsonify({"error": f"路径访问权限不足: {e}"}), 400
    except Exception as e:
        logger.error(f"路径预览失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
@app.route("/api/thumbnail", methods=["GET"])
@login_required
def api_thumbnail():
    """
    缩略图生成 API - 按需生成文件缩略图
    """
    try:
        file_path = request.args.get('path')
        if not file_path:
            return jsonify({"error": "缺少 path 参数"}), 400

        file_path = unquote(file_path)

        if not os.path.exists(file_path):
            return jsonify({"error": "文件不存在"}), 404

        size = int(request.args.get('size', 128))
        if size <= 0:
            size = 128

        os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
        cleanup_thumbnail_cache(THUMBNAIL_CACHE_DIR)

        mtime = os.path.getmtime(file_path)
        cache_key = hashlib.md5(f"{file_path}_{mtime}_{size}".encode('utf-8')).hexdigest()
        cache_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{cache_key}.jpg")

        if os.path.exists(cache_path):
            cache_age = time.time() - os.path.getmtime(cache_path)
            if cache_age < THUMBNAIL_CACHE_TTL:
                logger.debug(f"缩略图缓存命中: {file_path}")
                return send_file(cache_path, mimetype='image/jpeg')

        file_size = os.path.getsize(file_path)
        if file_size > THUMBNAIL_LARGE_FILE_THRESHOLD:
            logger.warning(f"文件过大，使用占位缩略图: {file_path}")
            return serve_default_thumbnail(size)

        def build_thumbnail_image():
            ext = os.path.splitext(file_path)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                return resize_image_with_aspect_ratio(file_path, (size, size), convert_rgb=True)
            if ext in VIDEO_EXTENSIONS:
                import cv2
                video = cv2.VideoCapture(file_path)
                success, frame = video.read()
                video.release()
                if not success:
                    raise RuntimeError("无法提取视频帧")
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = PILImage.fromarray(frame_rgb)
                img.thumbnail((size, size), PILImage.Resampling.LANCZOS)
                return img
            if ext == '.pdf':
                try:
                    from pdf2image import convert_from_path
                except ImportError:
                    raise RuntimeError("缺少 pdf2image 依赖")
                images = convert_from_path(file_path, first_page=1, last_page=1, size=(size, size))
                if not images:
                    raise RuntimeError("无法渲染 PDF 页面")
                img = images[0]
                img.thumbnail((size, size), PILImage.Resampling.LANCZOS)
                return img
            raise ValueError("不支持的文件类型")

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(build_thumbnail_image)
                img = future.result(timeout=THUMBNAIL_TIMEOUT_SECONDS)
        except FuturesTimeoutError:
            logger.warning(f"生成缩略图超时，返回占位图: {file_path}")
            return serve_default_thumbnail(size)
        except ValueError as unsupported_err:
            return jsonify({"error": str(unsupported_err)}), 400

        img.save(cache_path, 'JPEG', quality=85)
        return send_file(cache_path, mimetype='image/jpeg')

    except RuntimeError as runtime_err:
        logger.error(f"缩略图生成失败: {runtime_err}")
        return jsonify({"error": str(runtime_err)}), 500
    except Exception as e:
        logger.error(f"缩略图生成失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
@app.route("/api/batch_index", methods=["POST"])
@login_required
def api_batch_index():
    """
    批量索引 API - 接收文件路径列表,启动后台索引任务
    """
    try:
        cleanup_indexing_tasks()
        data = request.json or {}
        if 'files' not in data or 'target' not in data:
            return jsonify({"error": "缺少必要参数"}), 400

        files = data.get('files')
        target = data.get('target')
        duplicate_strategy = str(data.get('duplicate_strategy', 'ask')).lower()

        if not isinstance(files, list) or len(files) == 0:
            return jsonify({"error": "files 必须是非空数组"}), 400

        if duplicate_strategy not in {'ask', 'skip', 'overwrite'}:
            return jsonify({"error": "duplicate_strategy 仅支持 ask/skip/overwrite"}), 400

        logger.info(f"批量索引请求: {len(files)} 个文件, target={target}, strategy={duplicate_strategy}")

        task_id = str(uuid.uuid4())
        now = time.time()
        indexing_tasks[task_id] = {
            'total': len(files),
            'processed': 0,
            'success': 0,
            'failed': [],
            'duplicates': [],
            'current_file': '',
            'status': 'running',
            'cancelled': False,
            'start_time': now,
            'updated_at': now,
            'duplicate_strategy': duplicate_strategy,
            'pending_duplicate': None
        }
        indexing_task_events[task_id] = threading.Event()
        indexing_task_decisions.pop(task_id, None)

        thread = threading.Thread(
            target=process_batch_index,
            args=(task_id, files, target, duplicate_strategy)
        )
        thread.daemon = True
        thread.start()

        return jsonify({"task_id": task_id})

    except Exception as e:
        logger.error(f"批量索引启动失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def wait_for_duplicate_decision(task_id: str, duplicate_payload: dict) -> str:
    """在 ask 模式下等待前端决策。"""
    task = indexing_tasks.get(task_id)
    if not task:
        return 'skip'

    event = indexing_task_events.setdefault(task_id, threading.Event())
    task['pending_duplicate'] = duplicate_payload
    task['status'] = 'waiting_duplicate'
    task['updated_at'] = time.time()
    event.clear()

    decision = None
    if event.wait(MAX_DUPLICATE_WAIT_SECONDS):
        decision = indexing_task_decisions.pop(task_id, None)

    if not decision:
        decision = {'action': 'skip', 'apply_to_all': False}

    task['pending_duplicate'] = None
    task['status'] = 'running'
    task['updated_at'] = time.time()

    action = decision.get('action', 'skip')
    if decision.get('apply_to_all') and action in {'skip', 'overwrite'}:
        task['duplicate_strategy'] = action

    return action


def process_batch_index(task_id, files, target, duplicate_strategy):
    """
    后台处理批量索引任务
    """
    task = indexing_tasks.get(task_id)
    if not task:
        return

    try:
        if target == 'permanent':
            db_session = get_db_manager().get_permanent_session()
        elif target.startswith('proj_'):
            db_session = get_db_manager().get_project_session(target)
        else:
            task['status'] = 'failed'
            task['error'] = f"无效的目标库: {target}"
            task['updated_at'] = time.time()
            return

        for idx, file_info in enumerate(files):
            if task.get('cancelled'):
                task['status'] = 'cancelled'
                task['updated_at'] = time.time()
                logger.info(f"任务 {task_id} 被取消 ({task['processed']}/{task['total']})")
                return

            file_path = file_info.get('path')
            task['current_file'] = file_info.get('filename', os.path.basename(file_path))
            task['processed'] = idx + 1
            task['updated_at'] = time.time()

            try:
                if not os.path.exists(file_path):
                    task['failed'].append({'path': file_path, 'error': '文件不存在'})
                    continue

                ext = os.path.splitext(file_path)[1].lower()
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                checksum = get_file_hash(file_path) if ENABLE_CHECKSUM else None

                if ext in IMAGE_EXTENSIONS:
                    props = calculate_image_properties(file_path)
                    if not props:
                        task['failed'].append({'path': file_path, 'error': '无法读取图片属性'})
                        continue

                    existing = None
                    strategy_for_this = task.get('duplicate_strategy', duplicate_strategy)
                    if props.get('phash'):
                        with db_session:
                            existing = db_session.query(Image).filter(Image.phash == props['phash']).first()

                    if existing:
                        action = strategy_for_this
                        if action == 'ask':
                            duplicate_payload = {
                                'new_file': {
                                    'path': file_path,
                                    'filename': os.path.basename(file_path),
                                    'size': props.get('file_size') or os.path.getsize(file_path),
                                    'mtime': int(os.path.getmtime(file_path)),
                                    'thumbnail': f"/api/thumbnail?path={quote(file_path, safe='')}&size=96"
                                },
                                'existing_file': {
                                    'path': existing.path,
                                    'filename': os.path.basename(existing.path),
                                    'size': getattr(existing, 'file_size', None),
                                    'mtime': int(existing.modify_time.timestamp()) if getattr(existing, 'modify_time', None) else None,
                                    'thumbnail': f"/api/thumbnail?path={quote(existing.path, safe='')}&size=96"
                                }
                            }
                            action = wait_for_duplicate_decision(task_id, duplicate_payload)

                        if action == 'skip':
                            task['duplicates'].append({
                                'path': file_path,
                                'existing_path': existing.path,
                                'action': '用户跳过' if strategy_for_this == 'ask' else '已跳过'
                            })
                            continue
                        if action == 'overwrite':
                            task['duplicates'].append({
                                'path': file_path,
                                'existing_path': existing.path,
                                'action': '用户覆盖' if strategy_for_this == 'ask' else '已覆盖'
                            })
                            with db_session:
                                db_session.delete(existing)
                                db_session.commit()

                    feature = process_image(file_path)
                    if feature is None:
                        task['failed'].append({'path': file_path, 'error': '特征提取失败'})
                        continue

                    with db_session:
                        add_image(
                            db_session,
                            path=file_path,
                            modify_time=mtime,
                            checksum=checksum,
                            features=feature.tobytes(),
                            **props
                        )

                    task['success'] += 1

                elif ext in VIDEO_EXTENSIONS:
                    frame_time_features_generator = process_video(file_path)
                    if frame_time_features_generator is None:
                        task['failed'].append({'path': file_path, 'error': '视频特征提取失败'})
                        continue

                    with db_session:
                        add_video(
                            db_session,
                            path=file_path,
                            modify_time=mtime,
                            checksum=checksum,
                            frame_time_features_generator=frame_time_features_generator
                        )

                    task['success'] += 1

                else:
                    task['failed'].append({'path': file_path, 'error': f'不支持的文件类型: {ext}'})

            except Exception as file_error:
                logger.error(f"索引文件失败 {file_path}: {file_error}", exc_info=True)
                task['failed'].append({'path': file_path, 'error': str(file_error)})

        task['status'] = 'completed'
        task['end_time'] = time.time()
        task['duration'] = task['end_time'] - task['start_time']
        task['updated_at'] = time.time()

        if target.startswith('proj_'):
            try:
                pm = get_project_manager()
                pm.update_project_stats(target)
            except Exception as stats_error:
                logger.error(f"更新项目统计失败: {stats_error}")

    except Exception as e:
        logger.error(f"批量索引任务失败: {e}", exc_info=True)
        if task:
            task['status'] = 'failed'
            task['error'] = str(e)
            task['updated_at'] = time.time()
    finally:
        indexing_task_events.pop(task_id, None)
        indexing_task_decisions.pop(task_id, None)


@app.route("/api/batch_index/<task_id>/decision", methods=["POST"])
@login_required
def api_batch_index_decision(task_id):
    """前端重复决策接口。"""
    cleanup_indexing_tasks()
    task = indexing_tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    if task.get('status') != 'waiting_duplicate':
        return jsonify({"error": "当前任务不需要重复决策"}), 400

    data = request.json or {}
    action = data.get('action')
    if action not in {'skip', 'overwrite'}:
        return jsonify({"error": "action 仅支持 skip/overwrite"}), 400

    apply_to_all = bool(data.get('apply_to_all'))
    indexing_task_decisions[task_id] = {
        'action': action,
        'apply_to_all': apply_to_all
    }
    event = indexing_task_events.setdefault(task_id, threading.Event())
    event.set()

    return jsonify({"success": True})
@app.route("/api/batch_index/<task_id>/status", methods=["GET"])
@login_required
def api_batch_index_status(task_id):
    """
    获取批量索引任务状态
    返回:
        {
            "total": 总文件数,
            "processed": 已处理数,
            "success": 成功数,
            "current_file": "当前文件名",
            "failed": [{path, error}, ...],
            "duplicates": [{path, existing_path, action}, ...],
            "status": "running/completed/failed/cancelled",
            "progress": 0.0-1.0
        }
    """
    try:
        cleanup_indexing_tasks()
        if task_id not in indexing_tasks:
            return jsonify({"error": "任务不存在"}), 404

        task = indexing_tasks[task_id]

        # 计算进度
        progress = task['processed'] / task['total'] if task['total'] > 0 else 0

        # 估算剩余时间
        remain_time = 0
        if task['processed'] > 0 and task['status'] == 'running':
            elapsed = time.time() - task['start_time']
            avg_time = elapsed / task['processed']
            remain_time = int(avg_time * (task['total'] - task['processed']))

        return jsonify({
            'total': task['total'],
            'processed': task['processed'],
            'success': task['success'],
            'current_file': task['current_file'],
            'failed': task['failed'],
            'duplicates': task['duplicates'],
            'status': task['status'],
            'progress': progress,
            'remain_time': remain_time,
            'pending_duplicate': task.get('pending_duplicate'),
            'duplicate_strategy': task.get('duplicate_strategy')
        })

    except Exception as e:
        logger.error(f"获取任务状态失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/batch_index/<task_id>", methods=["DELETE"])
@login_required
def api_batch_index_cancel(task_id):
    """
    取消批量索引任务
    返回:
        {"message": "任务已取消"}
    """
    try:
        cleanup_indexing_tasks()
        if task_id not in indexing_tasks:
            return jsonify({"error": "任务不存在"}), 404

        task = indexing_tasks[task_id]

        if task['status'] in ['completed', 'failed', 'cancelled']:
            return jsonify({"error": f"任务已{task['status']}，无法取消"}), 400

        # 设置取消标志
        task['cancelled'] = True

        logger.info(f"任务 {task_id} 取消请求已发送")

        return jsonify({
            "message": "任务取消请求已发送",
            "processed": task['processed'],
            "total": task['total']
        })

    except Exception as e:
        logger.error(f"取消任务失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# 执行加密路由代码（在新路由定义之后，避免被覆盖）
with open('routes_encrypted.py', encoding='utf-8') as f:
    code = f.read()
exec(code)




