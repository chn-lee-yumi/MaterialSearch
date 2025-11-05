#!/usr/bin/env python3
"""
数据库迁移回滚脚本
从备份文件恢复数据库
"""

import os
import sys
import shutil
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def rollback_database(db_path: str, backup_path: str):
    """
    从备份恢复数据库

    Args:
        db_path: 数据库文件路径
        backup_path: 备份文件路径
    """
    if not os.path.exists(backup_path):
        logger.error(f"备份文件不存在: {backup_path}")
        return False

    try:
        logger.info(f"开始回滚数据库...")
        logger.info(f"  目标: {db_path}")
        logger.info(f"  备份: {backup_path}")

        # 如果当前数据库存在，先备份为 .rollback
        if os.path.exists(db_path):
            rollback_backup = f"{db_path}.rollback"
            shutil.copy2(db_path, rollback_backup)
            logger.info(f"  当前数据库已备份为: {rollback_backup}")

        # 恢复备份
        shutil.copy2(backup_path, db_path)

        logger.info("回滚成功完成！")
        return True

    except Exception as e:
        logger.error(f"回滚失败: {e}")
        return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='数据库迁移回滚脚本')
    parser.add_argument('--db', type=str, default='./instance/assets.db',
                        help='数据库文件路径')
    parser.add_argument('--backup', type=str, required=True,
                        help='备份文件路径')
    args = parser.parse_args()

    rollback_database(args.db, args.backup)


if __name__ == '__main__':
    main()
