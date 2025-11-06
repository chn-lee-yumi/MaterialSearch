"""
归档功能模块
负责将项目库中的图片/视频归档到永久库
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from models import Image, ProjectImage, ProjectVideo
from database import get_db_manager

logger = logging.getLogger(__name__)


class ArchiveManager:
    """归档管理器"""

    def __init__(self):
        """初始化归档管理器"""
        self.db_manager = get_db_manager()

    def archive_images_to_permanent(self,
                                     project_id: str,
                                     image_ids: List[int],
                                     mark_archived: bool = True) -> Dict:
        """
        将项目库中的图片归档到永久库

        Args:
            project_id: 项目 ID
            image_ids: 要归档的图片 ID 列表
            mark_archived: 是否标记项目库中的图片为已归档

        Returns:
            Dict: 归档结果
                {
                    'success': int,  # 成功归档数量
                    'failed': int,   # 失败数量
                    'errors': List[str]  # 错误信息列表
                }
        """
        success_count = 0
        failed_count = 0
        errors = []

        project_session = None
        permanent_session = None

        try:
            project_session = self.db_manager.get_project_session(project_id)
            permanent_session = self.db_manager.get_permanent_session()

            for image_id in image_ids:
                try:
                    # 从项目库读取图片记录
                    project_image = project_session.query(ProjectImage).filter_by(
                        id=image_id,
                        is_deleted=False
                    ).first()

                    if not project_image:
                        errors.append(f"图片不存在或已删除: ID={image_id}")
                        failed_count += 1
                        continue

                    # 检查是否已归档
                    if project_image.archived:
                        logger.warning(f"图片已归档: {project_image.path}")
                        errors.append(f"图片已归档: {project_image.path}")
                        failed_count += 1
                        continue

                    # 创建永久库记录（复制所有字段）
                    permanent_image = Image(
                        path=project_image.path,
                        modify_time=project_image.modify_time,
                        features=project_image.features,  # 直接复制向量，不重新计算
                        checksum=project_image.checksum,
                        # 文件属性
                        width=project_image.width,
                        height=project_image.height,
                        aspect_ratio=project_image.aspect_ratio,
                        aspect_ratio_standard=project_image.aspect_ratio_standard,
                        file_size=project_image.file_size,
                        file_format=project_image.file_format,
                        # 时间戳
                        upload_time=project_image.upload_time,
                        last_accessed=project_image.last_accessed,
                        # 分类标签
                        category=project_image.category,
                        sub_category=project_image.sub_category,
                        tags=project_image.tags,
                        building_type=project_image.building_type,
                        design_style=project_image.design_style,
                        # 来源信息（标注来自项目归档）
                        source_type='project_archive',
                        source_project=project_id,
                        source_notes=f"归档自项目: {project_id}",
                        # 质量管理
                        quality_score=project_image.quality_score,
                        is_featured=project_image.is_featured,
                        # 去重
                        phash=project_image.phash,
                        duplicate_group=project_image.duplicate_group,
                        is_duplicate=project_image.is_duplicate,
                        # AI 增强
                        ai_description=project_image.ai_description,
                        ai_description_vector=project_image.ai_description_vector,
                    )

                    permanent_session.add(permanent_image)
                    permanent_session.flush()  # 获取新 ID

                    # 标记项目库记录为已归档
                    if mark_archived:
                        project_image.archived = True
                        project_image.archived_to_id = permanent_image.id
                        project_image.archived_time = datetime.now()

                    # 原子提交：先提交 permanent，如果成功再提交 project
                    try:
                        permanent_session.commit()
                        try:
                            project_session.commit()
                        except Exception as project_error:
                            # project 提交失败，删除已提交的 permanent 记录
                            logger.error(f"项目库提交失败，回滚永久库记录: {project_error}")
                            permanent_session.delete(permanent_image)
                            permanent_session.commit()
                            raise
                    except Exception as commit_error:
                        # 任一提交失败，回滚未提交的会话
                        permanent_session.rollback()
                        project_session.rollback()
                        raise

                    success_count += 1
                    logger.info(f"归档成功: {project_image.path} -> {permanent_image.id}")

                except Exception as e:
                    # 回滚当前图片的失败操作
                    permanent_session.rollback()
                    project_session.rollback()
                    logger.error(f"归档图片失败 ID={image_id}: {e}")
                    errors.append(f"ID={image_id}: {str(e)}")
                    failed_count += 1

            logger.info(f"归档完成: 成功 {success_count}, 失败 {failed_count}")

            return {
                'success': success_count,
                'failed': failed_count,
                'errors': errors
            }

        except Exception as e:
            logger.error(f"归档过程失败: {e}")
            if permanent_session:
                permanent_session.rollback()
            if project_session:
                project_session.rollback()
            raise

        finally:
            if permanent_session:
                permanent_session.close()
            if project_session:
                project_session.close()

    def archive_videos_to_permanent(self,
                                     project_id: str,
                                     video_paths: List[str],
                                     mark_archived: bool = True) -> Dict:
        """
        将项目库中的视频归档到永久库

        Args:
            project_id: 项目 ID
            video_paths: 要归档的视频路径列表
            mark_archived: 是否标记项目库中的视频为已归档

        Returns:
            Dict: 归档结果
        """
        # 视频归档逻辑类似图片，暂时简化实现
        logger.warning("视频归档功能尚未完全实现")
        return {
            'success': 0,
            'failed': len(video_paths),
            'errors': ['视频归档功能尚未完全实现']
        }

    def get_archived_images(self, project_id: str) -> List[Dict]:
        """
        获取项目中已归档的图片列表

        Args:
            project_id: 项目 ID

        Returns:
            List[Dict]: 已归档图片信息列表
        """
        project_session = None
        try:
            project_session = self.db_manager.get_project_session(project_id)

            archived_images = project_session.query(ProjectImage).filter_by(
                archived=True,
                is_deleted=False
            ).all()

            return [
                {
                    'id': img.id,
                    'path': img.path,
                    'archived_to_id': img.archived_to_id,
                    'archived_time': img.archived_time.isoformat() if img.archived_time else None,
                }
                for img in archived_images
            ]

        finally:
            if project_session:
                project_session.close()

    def unarchive_images(self, project_id: str, image_ids: List[int]) -> Dict:
        """
        取消归档标记（不删除永久库中的记录）

        Args:
            project_id: 项目 ID
            image_ids: 图片 ID 列表

        Returns:
            Dict: 操作结果
        """
        project_session = None
        success_count = 0

        try:
            project_session = self.db_manager.get_project_session(project_id)

            for image_id in image_ids:
                project_image = project_session.query(ProjectImage).filter_by(
                    id=image_id
                ).first()

                if project_image and project_image.archived:
                    project_image.archived = False
                    project_image.archived_to_id = None
                    project_image.archived_time = None
                    success_count += 1

            project_session.commit()

            return {
                'success': success_count,
                'message': f'取消归档标记: {success_count} 张图片'
            }

        except Exception as e:
            if project_session:
                project_session.rollback()
            logger.error(f"取消归档失败: {e}")
            raise

        finally:
            if project_session:
                project_session.close()


# 全局归档管理器实例
_archive_manager: Optional[ArchiveManager] = None


def get_archive_manager() -> ArchiveManager:
    """获取全局归档管理器实例"""
    global _archive_manager
    if _archive_manager is None:
        _archive_manager = ArchiveManager()
    return _archive_manager
