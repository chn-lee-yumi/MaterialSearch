#!/usr/bin/env python3
"""
数据库迁移脚本
将现有数据库迁移到新的 Schema（添加项目管理相关字段）
"""

import os
import sys
import shutil
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image as PILImage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseMigration:
    """数据库迁移管理器"""

    def __init__(self, db_path: str):
        """
        初始化迁移管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.backup_path = None
        self.conn = None

    def backup_database(self) -> str:
        """
        备份数据库文件

        Returns:
            str: 备份文件路径
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(os.path.dirname(self.db_path), 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        backup_filename = f"{os.path.basename(self.db_path)}.backup_{timestamp}"
        self.backup_path = os.path.join(backup_dir, backup_filename)

        logger.info(f"开始备份数据库: {self.db_path}")
        shutil.copy2(self.db_path, self.backup_path)
        logger.info(f"备份完成: {self.backup_path}")

        return self.backup_path

    def connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        logger.info(f"已连接到数据库: {self.db_path}")

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")

    def add_new_fields(self):
        """添加新字段到 image 和 video 表"""
        cursor = self.conn.cursor()

        # Image 表新增字段
        image_fields = [
            # 文件属性
            "ALTER TABLE image ADD COLUMN width INTEGER",
            "ALTER TABLE image ADD COLUMN height INTEGER",
            "ALTER TABLE image ADD COLUMN aspect_ratio REAL",
            "ALTER TABLE image ADD COLUMN aspect_ratio_standard TEXT",
            "ALTER TABLE image ADD COLUMN file_size INTEGER",
            "ALTER TABLE image ADD COLUMN file_format TEXT",

            # 时间戳
            "ALTER TABLE image ADD COLUMN upload_time DATETIME",
            "ALTER TABLE image ADD COLUMN last_accessed DATETIME",

            # 分类标签
            "ALTER TABLE image ADD COLUMN category TEXT",
            "ALTER TABLE image ADD COLUMN sub_category TEXT",
            "ALTER TABLE image ADD COLUMN tags TEXT",
            "ALTER TABLE image ADD COLUMN building_type TEXT",
            "ALTER TABLE image ADD COLUMN design_style TEXT",

            # 来源信息
            "ALTER TABLE image ADD COLUMN source_type TEXT DEFAULT 'local'",
            "ALTER TABLE image ADD COLUMN source_project TEXT",
            "ALTER TABLE image ADD COLUMN source_notes TEXT",

            # 质量管理
            "ALTER TABLE image ADD COLUMN quality_score REAL",
            "ALTER TABLE image ADD COLUMN is_featured INTEGER DEFAULT 0",

            # 去重预留
            "ALTER TABLE image ADD COLUMN phash TEXT",
            "ALTER TABLE image ADD COLUMN duplicate_group TEXT",
            "ALTER TABLE image ADD COLUMN is_duplicate INTEGER DEFAULT 0",

            # AI 增强
            "ALTER TABLE image ADD COLUMN ai_description TEXT",
            "ALTER TABLE image ADD COLUMN ai_description_vector BLOB",

            # 软删除
            "ALTER TABLE image ADD COLUMN is_deleted INTEGER DEFAULT 0",
            "ALTER TABLE image ADD COLUMN deleted_time DATETIME",
        ]

        # Video 表新增字段
        video_fields = [
            # 文件属性
            "ALTER TABLE video ADD COLUMN width INTEGER",
            "ALTER TABLE video ADD COLUMN height INTEGER",
            "ALTER TABLE video ADD COLUMN aspect_ratio REAL",
            "ALTER TABLE video ADD COLUMN duration INTEGER",
            "ALTER TABLE video ADD COLUMN file_size INTEGER",
            "ALTER TABLE video ADD COLUMN file_format TEXT",

            # 时间戳
            "ALTER TABLE video ADD COLUMN upload_time DATETIME",
            "ALTER TABLE video ADD COLUMN last_accessed DATETIME",

            # 分类标签
            "ALTER TABLE video ADD COLUMN category TEXT",
            "ALTER TABLE video ADD COLUMN sub_category TEXT",
            "ALTER TABLE video ADD COLUMN tags TEXT",
            "ALTER TABLE video ADD COLUMN building_type TEXT",
            "ALTER TABLE video ADD COLUMN design_style TEXT",

            # 来源信息
            "ALTER TABLE video ADD COLUMN source_type TEXT DEFAULT 'local'",
            "ALTER TABLE video ADD COLUMN source_project TEXT",
            "ALTER TABLE video ADD COLUMN source_notes TEXT",

            # 质量管理
            "ALTER TABLE video ADD COLUMN quality_score REAL",
            "ALTER TABLE video ADD COLUMN is_featured INTEGER DEFAULT 0",

            # AI 增强
            "ALTER TABLE video ADD COLUMN ai_description TEXT",
            "ALTER TABLE video ADD COLUMN ai_description_vector BLOB",

            # 软删除
            "ALTER TABLE video ADD COLUMN is_deleted INTEGER DEFAULT 0",
            "ALTER TABLE video ADD COLUMN deleted_time DATETIME",
        ]

        logger.info("开始添加新字段...")

        # 添加 Image 表字段
        for sql in image_fields:
            try:
                cursor.execute(sql)
                field_name = sql.split("ADD COLUMN")[1].split()[0]
                logger.info(f"  ✓ Image 表添加字段: {field_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    logger.warning(f"  ⚠ 字段已存在，跳过")
                else:
                    raise

        # 添加 Video 表字段
        for sql in video_fields:
            try:
                cursor.execute(sql)
                field_name = sql.split("ADD COLUMN")[1].split()[0]
                logger.info(f"  ✓ Video 表添加字段: {field_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    logger.warning(f"  ⚠ 字段已存在，跳过")
                else:
                    raise

        self.conn.commit()
        logger.info("字段添加完成")

    def calculate_image_properties(self):
        """计算现有图片的属性（宽度、高度、宽高比等）"""
        cursor = self.conn.cursor()

        # 获取所有需要更新的图片
        cursor.execute("SELECT id, path FROM image WHERE width IS NULL")
        images = cursor.fetchall()

        total = len(images)
        logger.info(f"开始计算图片属性，共 {total} 张图片")

        success_count = 0
        fail_count = 0

        for idx, row in enumerate(images, 1):
            image_id = row[0]
            image_path = row[1]

            try:
                # 检查文件是否存在
                if not os.path.exists(image_path):
                    logger.warning(f"  [{idx}/{total}] 文件不存在: {image_path}")
                    fail_count += 1
                    continue

                # 读取图片
                with PILImage.open(image_path) as img:
                    width, height = img.size
                    aspect_ratio = round(width / height, 3)
                    aspect_ratio_standard = self._get_standard_aspect_ratio(aspect_ratio)
                    file_size = os.path.getsize(image_path)
                    file_format = img.format.lower() if img.format else os.path.splitext(image_path)[1][1:].lower()

                    # 更新数据库
                    cursor.execute("""
                        UPDATE image
                        SET width = ?, height = ?, aspect_ratio = ?,
                            aspect_ratio_standard = ?, file_size = ?, file_format = ?
                        WHERE id = ?
                    """, (width, height, aspect_ratio, aspect_ratio_standard, file_size, file_format, image_id))

                    success_count += 1

                    if idx % 100 == 0:
                        self.conn.commit()
                        logger.info(f"  进度: {idx}/{total} ({success_count} 成功, {fail_count} 失败)")

            except Exception as e:
                logger.error(f"  [{idx}/{total}] 处理失败 {image_path}: {e}")
                fail_count += 1

        self.conn.commit()
        logger.info(f"图片属性计算完成: {success_count} 成功, {fail_count} 失败")

    def _get_standard_aspect_ratio(self, ratio: float) -> str:
        """
        获取标准宽高比

        Args:
            ratio: 实际宽高比

        Returns:
            str: 标准宽高比字符串
        """
        standard_ratios = {
            1.0: "1:1",
            1.333: "4:3",
            1.5: "3:2",
            1.6: "16:10",
            1.778: "16:9",
            2.0: "2:1",
            2.333: "21:9",
            0.75: "3:4",
            0.667: "2:3",
            0.5625: "9:16",
        }

        # 找到最接近的标准比例
        min_diff = float('inf')
        result = f"{ratio:.2f}:1"

        for standard_ratio, label in standard_ratios.items():
            diff = abs(ratio - standard_ratio)
            if diff < min_diff:
                min_diff = diff
                result = label

        # 如果差异小于 0.05，认为是标准比例
        if min_diff > 0.05:
            result = f"{ratio:.2f}:1"

        return result

    def create_indexes(self):
        """创建索引"""
        cursor = self.conn.cursor()

        indexes = [
            # Image 表索引
            "CREATE INDEX IF NOT EXISTS idx_image_aspect_ratio ON image(aspect_ratio)",
            "CREATE INDEX IF NOT EXISTS idx_image_aspect_ratio_standard ON image(aspect_ratio_standard)",
            "CREATE INDEX IF NOT EXISTS idx_image_category ON image(category)",
            "CREATE INDEX IF NOT EXISTS idx_image_design_style ON image(design_style)",
            "CREATE INDEX IF NOT EXISTS idx_image_phash ON image(phash)",
            "CREATE INDEX IF NOT EXISTS idx_image_is_deleted ON image(is_deleted)",

            # Video 表索引
            "CREATE INDEX IF NOT EXISTS idx_video_aspect_ratio ON video(aspect_ratio)",
            "CREATE INDEX IF NOT EXISTS idx_video_category ON video(category)",
            "CREATE INDEX IF NOT EXISTS idx_video_design_style ON video(design_style)",
            "CREATE INDEX IF NOT EXISTS idx_video_is_deleted ON video(is_deleted)",
        ]

        logger.info("开始创建索引...")

        for sql in indexes:
            try:
                cursor.execute(sql)
                index_name = sql.split("CREATE INDEX IF NOT EXISTS")[1].split()[0]
                logger.info(f"  ✓ 创建索引: {index_name}")
            except Exception as e:
                logger.error(f"  ✗ 索引创建失败: {e}")

        self.conn.commit()
        logger.info("索引创建完成")

    def verify_migration(self):
        """验证迁移结果"""
        cursor = self.conn.cursor()

        logger.info("开始验证迁移结果...")

        # 检查字段是否存在
        cursor.execute("PRAGMA table_info(image)")
        image_columns = [row[1] for row in cursor.fetchall()]

        new_fields = ['width', 'height', 'aspect_ratio', 'aspect_ratio_standard',
                      'file_size', 'file_format', 'category', 'tags', 'is_deleted']

        for field in new_fields:
            if field in image_columns:
                logger.info(f"  ✓ 字段存在: image.{field}")
            else:
                logger.error(f"  ✗ 字段缺失: image.{field}")

        # 统计已计算属性的图片数量
        cursor.execute("SELECT COUNT(*) FROM image WHERE width IS NOT NULL")
        count_with_props = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM image")
        total_count = cursor.fetchone()[0]

        logger.info(f"  图片总数: {total_count}")
        logger.info(f"  已计算属性: {count_with_props}")
        logger.info(f"  完成率: {count_with_props / total_count * 100:.1f}%" if total_count > 0 else "  完成率: 0%")

        logger.info("验证完成")

    def run(self):
        """执行完整迁移流程"""
        try:
            logger.info("=" * 60)
            logger.info("开始数据库迁移")
            logger.info("=" * 60)

            # 1. 备份
            self.backup_database()

            # 2. 连接数据库
            self.connect()

            # 3. 添加新字段
            self.add_new_fields()

            # 4. 计算图片属性
            self.calculate_image_properties()

            # 5. 创建索引
            self.create_indexes()

            # 6. 验证
            self.verify_migration()

            logger.info("=" * 60)
            logger.info("迁移成功完成！")
            logger.info(f"备份文件: {self.backup_path}")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"迁移失败: {e}")
            logger.error(f"可以使用备份文件恢复: {self.backup_path}")
            raise

        finally:
            self.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='数据库迁移脚本')
    parser.add_argument('--db', type=str, default='./instance/assets.db',
                        help='数据库文件路径（默认: ./instance/assets.db）')
    args = parser.parse_args()

    migration = DatabaseMigration(args.db)
    migration.run()


if __name__ == '__main__':
    main()
