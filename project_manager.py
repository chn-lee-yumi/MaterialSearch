"""
项目管理模块
负责项目的创建、查询、更新、删除和统计信息管理
"""

import os
import logging
from typing import List, Optional, Dict
from datetime import datetime
import re

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models import Project, ProjectImage, ProjectVideo
from database import get_db_manager

logger = logging.getLogger(__name__)


class ProjectManager:
    """项目管理器"""

    def __init__(self):
        """初始化项目管理器"""
        self.db_manager = get_db_manager()

    def create_project(self,
                       name: str,
                       client_name: Optional[str] = None,
                       description: Optional[str] = None) -> Project:
        """
        创建新项目

        Args:
            name: 项目名称
            client_name: 客户名称
            description: 项目描述

        Returns:
            Project: 创建的项目对象

        Raises:
            ValueError: 项目名称无效或已存在
        """
        # 验证项目名称
        if not name or not name.strip():
            raise ValueError("项目名称不能为空")

        # 生成项目 ID
        project_id = self._generate_project_id(name)

        # 检查项目是否已存在
        session = self.db_manager.get_metadata_session()
        try:
            existing = session.query(Project).filter_by(id=project_id).first()
            if existing and not existing.is_deleted:
                raise ValueError(f"项目 ID 已存在: {project_id}")

            # 创建项目数据库
            db_path = self.db_manager.create_project_database(project_id)

            # 创建项目记录
            project = Project(
                id=project_id,
                name=name.strip(),
                client_name=client_name.strip() if client_name else None,
                description=description.strip() if description else None,
                status='active',
                created_time=datetime.now(),
                updated_time=datetime.now(),
                database_path=db_path,
                image_count=0,
                video_count=0,
                total_size=0,
                is_deleted=False
            )

            session.add(project)
            session.commit()
            session.refresh(project)

            logger.info(f"项目创建成功: {project_id} ({name})")
            return project

        except Exception as e:
            session.rollback()
            logger.error(f"项目创建失败: {e}")
            raise
        finally:
            session.close()

    def _generate_project_id(self, name: str) -> str:
        """
        生成项目 ID

        格式: proj_YYYY_名称_序号

        Args:
            name: 项目名称

        Returns:
            str: 项目 ID
        """
        year = datetime.now().year
        # 清理名称（移除特殊字符）
        clean_name = re.sub(r'[^\w\u4e00-\u9fff]+', '_', name)
        clean_name = clean_name.strip('_')[:20]  # 限制长度

        # 查找同名项目的数量，生成序号
        session = self.db_manager.get_metadata_session()
        try:
            prefix = f"proj_{year}_{clean_name}"
            existing = session.query(Project).filter(
                Project.id.like(f"{prefix}%")
            ).count()

            sequence = existing + 1
            project_id = f"{prefix}_{sequence:02d}"

            return project_id
        finally:
            session.close()

    def list_projects(self,
                      status: Optional[str] = None,
                      include_deleted: bool = False) -> List[Project]:
        """
        获取项目列表

        Args:
            status: 项目状态筛选 (active/completed/archived)
            include_deleted: 是否包含已删除的项目

        Returns:
            List[Project]: 项目列表
        """
        session = self.db_manager.get_metadata_session()
        try:
            query = session.query(Project)

            if not include_deleted:
                query = query.filter(Project.is_deleted == False)

            if status:
                query = query.filter(Project.status == status)

            projects = query.order_by(desc(Project.created_time)).all()
            return projects

        finally:
            session.close()

    def get_project(self, project_id: str) -> Optional[Project]:
        """
        获取项目详情

        Args:
            project_id: 项目 ID

        Returns:
            Optional[Project]: 项目对象，不存在则返回 None
        """
        session = self.db_manager.get_metadata_session()
        try:
            project = session.query(Project).filter_by(
                id=project_id,
                is_deleted=False
            ).first()
            return project
        finally:
            session.close()

    def update_project(self,
                       project_id: str,
                       name: Optional[str] = None,
                       client_name: Optional[str] = None,
                       description: Optional[str] = None,
                       status: Optional[str] = None) -> Project:
        """
        更新项目信息

        Args:
            project_id: 项目 ID
            name: 新的项目名称
            client_name: 新的客户名称
            description: 新的项目描述
            status: 新的项目状态

        Returns:
            Project: 更新后的项目对象

        Raises:
            ValueError: 项目不存在
        """
        session = self.db_manager.get_metadata_session()
        try:
            project = session.query(Project).filter_by(
                id=project_id,
                is_deleted=False
            ).first()

            if not project:
                raise ValueError(f"项目不存在: {project_id}")

            # 更新字段
            if name is not None:
                project.name = name.strip()
            if client_name is not None:
                project.client_name = client_name.strip() if client_name else None
            if description is not None:
                project.description = description.strip() if description else None
            if status is not None:
                if status not in ['active', 'completed', 'archived']:
                    raise ValueError(f"无效的状态: {status}")
                project.status = status

            project.updated_time = datetime.now()

            session.commit()
            session.refresh(project)

            logger.info(f"项目更新成功: {project_id}")
            return project

        except Exception as e:
            session.rollback()
            logger.error(f"项目更新失败: {e}")
            raise
        finally:
            session.close()

    def delete_project(self, project_id: str, hard_delete: bool = False) -> bool:
        """
        删除项目（软删除或硬删除）

        Args:
            project_id: 项目 ID
            hard_delete: 是否硬删除（删除数据库文件）

        Returns:
            bool: 删除成功返回 True

        Raises:
            ValueError: 项目不存在
        """
        session = self.db_manager.get_metadata_session()
        try:
            project = session.query(Project).filter_by(id=project_id).first()

            if not project:
                raise ValueError(f"项目不存在: {project_id}")

            if hard_delete:
                # 硬删除：先关闭数据库连接，避免 Windows 文件锁定
                self.db_manager.close_project_db(project_id)

                # 删除数据库文件
                if project.database_path and os.path.exists(project.database_path):
                    os.remove(project.database_path)
                    logger.info(f"项目数据库文件已删除: {project.database_path}")

                # 删除 WAL 文件
                wal_path = f"{project.database_path}-wal"
                shm_path = f"{project.database_path}-shm"
                if os.path.exists(wal_path):
                    os.remove(wal_path)
                if os.path.exists(shm_path):
                    os.remove(shm_path)

                # 从数据库中删除记录
                session.delete(project)
                logger.info(f"项目已硬删除: {project_id}")
            else:
                # 软删除：标记为已删除
                project.is_deleted = True
                project.updated_time = datetime.now()
                logger.info(f"项目已软删除: {project_id}")

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"项目删除失败: {e}")
            raise
        finally:
            session.close()

    def get_project_stats(self, project_id: str) -> Dict:
        """
        获取项目统计信息

        Args:
            project_id: 项目 ID

        Returns:
            Dict: 统计信息
        """
        # 获取项目基本信息
        session_meta = self.db_manager.get_metadata_session()
        try:
            project = session_meta.query(Project).filter_by(
                id=project_id,
                is_deleted=False
            ).first()

            if not project:
                raise ValueError(f"项目不存在: {project_id}")

            # 获取项目数据库的统计信息
            try:
                session_proj = self.db_manager.get_project_session(project_id)
                try:
                    image_count = session_proj.query(ProjectImage).filter(
                        ProjectImage.is_deleted == False
                    ).count()

                    video_count = session_proj.query(ProjectVideo).filter(
                        ProjectVideo.is_deleted == False
                    ).count()

                    # 计算总大小
                    total_size = 0
                    images = session_proj.query(ProjectImage.file_size).filter(
                        ProjectImage.is_deleted == False,
                        ProjectImage.file_size.isnot(None)
                    ).all()
                    total_size += sum(img.file_size or 0 for img in images)

                    videos = session_proj.query(ProjectVideo.file_size).filter(
                        ProjectVideo.is_deleted == False,
                        ProjectVideo.file_size.isnot(None)
                    ).all()
                    total_size += sum(vid.file_size or 0 for vid in videos)

                finally:
                    session_proj.close()

            except Exception as e:
                logger.warning(f"获取项目统计信息失败: {e}")
                image_count = project.image_count
                video_count = project.video_count
                total_size = project.total_size

            return {
                'project_id': project.id,
                'name': project.name,
                'client_name': project.client_name,
                'status': project.status,
                'image_count': image_count,
                'video_count': video_count,
                'total_size': total_size,
                'total_size_mb': round(total_size / 1024 / 1024, 2) if total_size else 0,
                'created_time': project.created_time.isoformat() if project.created_time else None,
                'updated_time': project.updated_time.isoformat() if project.updated_time else None,
            }

        finally:
            session_meta.close()

    def update_project_stats(self, project_id: str):
        """
        更新项目统计信息（存储在元信息库中）

        Args:
            project_id: 项目 ID
        """
        session_meta = self.db_manager.get_metadata_session()
        try:
            project = session_meta.query(Project).filter_by(id=project_id).first()
            if not project:
                raise ValueError(f"项目不存在: {project_id}")

            # 计算统计信息
            stats = self.get_project_stats(project_id)

            # 更新到元信息库
            project.image_count = stats['image_count']
            project.video_count = stats['video_count']
            project.total_size = stats['total_size']
            project.updated_time = datetime.now()

            session_meta.commit()
            logger.info(f"项目统计信息已更新: {project_id}")

        except Exception as e:
            session_meta.rollback()
            logger.error(f"更新项目统计信息失败: {e}")
            raise
        finally:
            session_meta.close()


# 全局项目管理器实例
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """获取全局项目管理器实例"""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager
