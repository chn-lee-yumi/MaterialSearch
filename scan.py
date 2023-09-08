import datetime
import logging
import pickle
import time
from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from app_base import app
from config import *
from database import Image, Video
from process_assets import process_image, process_video
from search import clean_cache

class Scanner:
    """
    扫描类
    """

    def __init__(self, app, db) -> None:
        # 全局变量
        self.app: Flask = app
        self.db: SQLAlchemy = db
        self.is_scanning = False
        self.scan_start_time = 0
        self.scanning_files = 0
        self.total_images = 0
        self.total_videos = 0
        self.total_video_frames = 0
        self.scanned_files = 0
        self.is_continue_scan = False
        self.logger = logging.getLogger(__name__)
        self.temp_file = f"{TEMP_PATH}/assets.pickle"
        self.assets = set()

        # 自动扫描时间
        self.start_time = datetime.time(*AUTO_SCAN_START_TIME)
        self.end_time = datetime.time(*AUTO_SCAN_END_TIME)
        self.is_cross_day = self.start_time > self.end_time  # 是否跨日期

        # 处理跳过路径
        self.skip_paths = [Path(i) for i in SKIP_PATH if i]
        self.ignore_keywords = [i for i in IGNORE_STRINGS if i]
        self.extensions = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS

    def init(self):
        self.total_images = self.db.session.query(Image).count()  # 获取图片总数
        self.total_videos = (
            self.db.session.query(Video.path).distinct().count()
        )  # 获取视频总数
        self.total_video_frames = self.db.session.query(Video).count()  # 获取视频帧总数

    def get_status(self):
        if self.scanned_files:
            remain_time = (
                (time.time() - self.scan_start_time)
                / self.scanned_files
                * self.scanning_files
            )
        else:
            remain_time = 0
        if self.is_scanning and self.scanning_files != 0:
            progress = self.scanned_files / self.scanning_files
        else:
            progress = 0
        return {
            "status": self.is_scanning,
            "total_images": self.total_images,
            "total_videos": self.total_videos,
            "total_video_frames": self.total_video_frames,
            "scanning_files": self.scanning_files,
            "remain_files": self.scanning_files - self.scanned_files,
            "progress": progress,
            "remain_time": int(remain_time),
            "enable_login": ENABLE_LOGIN,
        }

    def save_assets(self):
        with open(self.temp_file, "wb") as f:
            pickle.dump(self.assets, f)

    def filter_path(self, path) -> bool:
        """
        过滤跳过的路径
        """
        if type(path) == str:
            path = Path(path)
        wrong_ext = path.suffix not in self.extensions
        skip = any((path.is_relative_to(p) for p in self.skip_paths))
        ignore = any((keyword in str(path).lower() for keyword in self.ignore_keywords))
        self.logger.debug(f"{path} 不匹配后缀：{wrong_ext} 跳过：{skip} 忽略： {ignore}")
        return not any((wrong_ext, skip, ignore))

    def generate_or_load_assets(self):
        if os.path.isfile(self.temp_file):
            self.logger.info("读取上次的目录缓存")
            self.is_continue_scan = True
            with open(self.temp_file, "rb") as f:
                self.assets = pickle.load(f)
            self.assets = set((i for i in filter(self.filter_path, self.assets)))
        else:
            self.is_continue_scan = False
            self.scan_dir()
            self.save_assets()

    def is_current_auto_scan_time(self) -> bool:
        """
        判断当前时间是否在自动扫描时间段内
        :return: 当前时间是否在自动扫描时间段内时返回True，否则返回False
        """
        current_time = datetime.datetime.now().time()
        is_in_range = (
            self.start_time <= current_time < self.end_time
        )  # 当前时间是否在 start_time 与 end_time 区间内
        return self.is_cross_day ^ is_in_range  # 跨日期与在区间内异或时，在自动扫描时间内

    def delete_record_if_not_exist(self) -> bool:
        for file in self.db.session.query(Image):
            if file.path not in self.assets:
                self.logger.info(f"文件已删除：{file.path}")
                self.db.session.delete(file)
        for path in self.db.session.query(Video.path).distinct():
            path = path[0]
            if path not in self.assets:
                self.logger.info(f"文件已删除：{path}")
                self.db.session.query(Video).filter_by(path=path).delete()
        self.db.session.commit()

    def auto_scan(self):
        """
        自动扫描，每5秒判断一次时间，如果在目标时间段内则开始扫描。
        :return: None
        """
        while True:
            time.sleep(5)
            if self.is_scanning or not self.is_current_auto_scan_time():
                continue
            self.logger.info("触发自动扫描")
            self.scan(auto=True)

    def scan_dir(self):
        """
        遍历文件并将符合条件的文件加入 assets 集合
        :return: None
        """
        self.assets = set()
        paths = [Path(i) for i in ASSETS_PATH if i]
        # 避免包含空字符串导致删库的情况
        skip_paths = [Path(i) for i in SKIP_PATH if i]
        ignore_keywords = [i for i in IGNORE_STRINGS if i]
        extensions = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS
        # 遍历根目录及其子目录下的所有文件
        for path in paths:
            for file in filter(lambda x: x.is_file(), path.rglob("*")):
                wrong_ext = file.suffix not in extensions
                skip = any((p in file for p in skip_paths))
                ignore = any(
                    (keyword in str(file).lower() for keyword in ignore_keywords)
                )
                self.logger.debug(f"{path} 不匹配后缀：{wrong_ext} 跳过：{skip} 忽略： {ignore}")
                if any((wrong_ext, skip, ignore)):
                    continue
                self.assets.add(str(file))

    def scan(self, auto=False):
        """
        扫描资源。如果存在assets.pickle，则直接读取并开始扫描。如果不存在，则先读取所有文件路径，并写入assets.pickle，然后开始扫描。
        每100个文件重新保存一次assets.pickle，如果程序被中断，下次可以从断点处继续扫描。扫描完成后删除assets.pickle并清缓存。
        :param auto: 是否由AUTO_SCAN触发的
        :return: None
        """
        self.logger.info("开始扫描")
        self.is_scanning = True
        self.scan_start_time = time.time()
        start_time = time.time()
        self.generate_or_load_assets()
        with app.app_context():
            # 删除不存在的文件记录
            if not self.is_continue_scan:  # 非断点恢复的情况下才删除
                self.delete_record_if_not_exist()
            # 扫描文件
            for path in self.assets.copy():
                self.scanned_files += 1
                if (
                    self.scanned_files % AUTO_SAVE_INTERVAL == 0
                ):  # 每扫描 AUTO_SAVE_INTERVAL 个文件重新save一下
                    self.save_assets()
                if auto and not self.is_current_auto_scan_time():  # 如果是自动扫描，判断时间自动停止
                    self.logger.info(f"超出自动扫描时间，停止扫描")
                    break
                # 如果文件不存在，则忽略（扫描时文件被移动或删除则会触发这种情况）
                if not os.path.isfile(path):
                    continue
                # 如果数据库里有这个文件，并且修改时间一致，则跳过，否则进行预处理并入库
                if path.lower().endswith(IMAGE_EXTENSIONS):  # 图片
                    db_record = (
                        self.db.session.query(Image).filter_by(path=path).first()
                    )
                    modify_time = datetime.datetime.fromtimestamp(
                        os.path.getmtime(path)
                    )
                    if db_record and db_record.modify_time == modify_time:
                        self.logger.debug(f"文件无变更，跳过：{path}")
                        self.assets.remove(path)
                        continue
                    features = process_image(path)
                    if features is None:
                        self.assets.remove(path)
                        continue
                    # 写入数据库
                    features = features.tobytes()
                    if db_record:
                        self.logger.info(f"文件有更新：{path}")
                        db_record.modify_time = modify_time
                        db_record.features = features
                    else:
                        self.logger.info(f"新增文件：{path}")
                        self.db.session.add(
                            Image(path=path, modify_time=modify_time, features=features)
                        )
                        self.total_images = self.db.session.query(
                            Image
                        ).count()  # 获取图片总数
                else:  # 视频
                    db_record = (
                        self.db.session.query(Video).filter_by(path=path).first()
                    )
                    modify_time = datetime.datetime.fromtimestamp(
                        os.path.getmtime(path)
                    )
                    if db_record and db_record.modify_time == modify_time:
                        self.logger.debug(f"文件无变更，跳过：{path}")
                        self.assets.remove(path)
                        continue
                    # 写入数据库
                    if db_record:
                        self.logger.info(f"文件有更新：{path}")
                        self.db.session.query(Video).filter_by(
                            path=path
                        ).delete()  # 视频文件直接删了重新写数据，而不是直接替换，因为视频长短可能有变化，不方便处理
                    else:
                        self.logger.info(f"新增文件：{path}")
                    # 使用 bulk_save_objects 一次性提交
                    self.db.session.bulk_save_objects(
                        [
                            Video(
                                path=path,
                                frame_time=frame_time,
                                modify_time=modify_time,
                                features=features.tobytes(),
                            )
                            for frame_time, features in process_video(path)
                        ]
                    )
                    self.total_video_frames = self.db.session.query(
                        Video
                    ).count()  # 获取视频帧总数
                    self.total_videos = (
                        self.db.session.query(Video.path).distinct().count()
                    )
                self.db.session.commit()  # 处理完一张图片或一个完整视频再commit，避免扫描视频到一半时程序中断，下次扫描会跳过这个视频的问题
                self.assets.remove(path)
            # 最后重新统计一下数量
            self.total_images = self.db.session.query(Image).count()  # 获取图片总数
            self.total_videos = (
                self.db.session.query(Video.path).distinct().count()
            )  # 获取视频总数
            self.total_video_frames = self.db.session.query(Video).count()  # 获取视频帧总数
        self.scanning_files = 0
        self.scanned_files = 0
        os.remove(self.temp_file)
        self.logger.info("扫描完成，用时%d秒" % int(time.time() - start_time))
        clean_cache()  # 清空搜索缓存
        self.is_scanning = False
