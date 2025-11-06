#!/usr/bin/env python3
"""
CLI 管理工具
提供命令行方式管理项目、执行迁移、查看统计等
"""

import sys
import click
import logging

from config import PERMANENT_DATABASE_PATH, METADATA_DATABASE_PATH, PROJECT_DATABASE_DIR
from database import init_database_manager, get_db_manager
from project_manager import get_project_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """MaterialSearch 项目管理工具"""
    pass


@cli.command()
def init():
    """初始化数据库结构"""
    click.echo("初始化数据库...")
    try:
        db_manager = init_database_manager(
            permanent_db_path=PERMANENT_DATABASE_PATH,
            metadata_db_path=METADATA_DATABASE_PATH,
            project_db_dir=PROJECT_DATABASE_DIR
        )
        click.echo(f"✓ 永久库: {PERMANENT_DATABASE_PATH}")
        click.echo(f"✓ 元信息库: {METADATA_DATABASE_PATH}")
        click.echo(f"✓ 项目目录: {PROJECT_DATABASE_DIR}")
        click.echo("数据库初始化完成！")
    except Exception as e:
        click.echo(f"✗ 初始化失败: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--db', default='./instance/assets.db', help='数据库文件路径')
def migrate(db):
    """执行数据迁移（添加新字段）"""
    click.echo(f"开始迁移数据库: {db}")
    try:
        from scripts.migrate_database import DatabaseMigration
        migration = DatabaseMigration(db)
        migration.run()
        click.echo("✓ 迁移完成！")
    except Exception as e:
        click.echo(f"✗ 迁移失败: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('name')
@click.option('--client', help='客户名称')
@click.option('--desc', help='项目描述')
def create_project(name, client, desc):
    """创建新项目"""
    click.echo(f"创建项目: {name}")
    try:
        pm = get_project_manager()
        project = pm.create_project(
            name=name,
            client_name=client,
            description=desc
        )
        click.echo(f"✓ 项目创建成功！")
        click.echo(f"  ID: {project.id}")
        click.echo(f"  名称: {project.name}")
        click.echo(f"  数据库: {project.database_path}")
    except Exception as e:
        click.echo(f"✗ 创建失败: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--status', type=click.Choice(['active', 'completed', 'archived']), help='按状态筛选')
def list_projects(status):
    """列出所有项目"""
    try:
        pm = get_project_manager()
        projects = pm.list_projects(status=status)

        if not projects:
            click.echo("没有找到项目。")
            return

        click.echo(f"\n共 {len(projects)} 个项目:\n")
        click.echo(f"{'ID':<35} {'名称':<20} {'状态':<10} {'图片数':<10} {'视频数':<10}")
        click.echo("-" * 95)

        for p in projects:
            click.echo(f"{p.id:<35} {p.name:<20} {p.status:<10} {p.image_count:<10} {p.video_count:<10}")

    except Exception as e:
        click.echo(f"✗ 获取项目列表失败: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('project_id')
def project_info(project_id):
    """查看项目详细信息"""
    try:
        pm = get_project_manager()
        stats = pm.get_project_stats(project_id)

        click.echo(f"\n项目信息:")
        click.echo(f"  ID: {stats['project_id']}")
        click.echo(f"  名称: {stats['name']}")
        click.echo(f"  客户: {stats['client_name'] or 'N/A'}")
        click.echo(f"  状态: {stats['status']}")
        click.echo(f"\n统计:")
        click.echo(f"  图片数: {stats['image_count']}")
        click.echo(f"  视频数: {stats['video_count']}")
        click.echo(f"  总大小: {stats['total_size_mb']} MB")
        click.echo(f"\n时间:")
        click.echo(f"  创建: {stats['created_time']}")
        click.echo(f"  更新: {stats['updated_time']}")

    except Exception as e:
        click.echo(f"✗ 获取项目信息失败: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('project_id')
@click.option('--hard', is_flag=True, help='硬删除（删除数据库文件）')
def delete_project(project_id, hard):
    """删除项目"""
    if hard:
        if not click.confirm(f'确认硬删除项目 {project_id}？数据库文件将被永久删除！'):
            click.echo("已取消")
            return

    try:
        pm = get_project_manager()
        pm.delete_project(project_id, hard_delete=hard)

        if hard:
            click.echo(f"✓ 项目已硬删除: {project_id}")
        else:
            click.echo(f"✓ 项目已软删除: {project_id}")

    except Exception as e:
        click.echo(f"✗ 删除失败: {e}", err=True)
        sys.exit(1)


@cli.command()
def stats():
    """显示系统统计信息"""
    try:
        pm = get_project_manager()
        projects = pm.list_projects()

        total_images = sum(p.image_count for p in projects)
        total_videos = sum(p.video_count for p in projects)
        total_size = sum(p.total_size for p in projects)
        total_size_mb = round(total_size / 1024 / 1024, 2)

        active_projects = [p for p in projects if p.status == 'active']
        completed_projects = [p for p in projects if p.status == 'completed']

        click.echo(f"\n系统统计:")
        click.echo(f"  项目总数: {len(projects)}")
        click.echo(f"    - 活跃: {len(active_projects)}")
        click.echo(f"    - 已完成: {len(completed_projects)}")
        click.echo(f"  图片总数: {total_images}")
        click.echo(f"  视频总数: {total_videos}")
        click.echo(f"  总大小: {total_size_mb} MB")

    except Exception as e:
        click.echo(f"✗ 获取统计信息失败: {e}", err=True)
        sys.exit(1)


@cli.command()
def backup():
    """手动执行数据库备份"""
    click.echo("功能开发中...")
    # TODO: 实现手动备份功能


if __name__ == '__main__':
    cli()
