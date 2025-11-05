#!/bin/bash
#
# 数据库恢复脚本
# 从备份文件恢复数据库
#

set -e

# 配置
DATA_DIR="${DATA_DIR:-./instance}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查参数
if [ -z "$1" ]; then
    log_error "用法: $0 <备份文件>"
    log_info "示例: $0 backups/20250105_030000.tar.gz"
    log_info ""
    log_info "可用的备份文件:"
    ls -lh "$BACKUP_DIR"/*.tar.gz 2>/dev/null || log_warn "没有找到备份文件"
    exit 1
fi

BACKUP_FILE="$1"

# 检查备份文件是否存在
if [ ! -f "$BACKUP_FILE" ]; then
    log_error "备份文件不存在: $BACKUP_FILE"
    exit 1
fi

log_warn "========================================="
log_warn "警告：恢复操作将覆盖现有数据库！"
log_warn "========================================="
log_info "备份文件: $BACKUP_FILE"
log_info "目标目录: $DATA_DIR"
echo ""
read -p "确认恢复？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    log_info "已取消"
    exit 0
fi

# 创建当前数据的备份（安全措施）
log_info "创建当前数据的安全备份..."
SAFE_BACKUP="$BACKUP_DIR/before_restore_$(date +%Y%m%d_%H%M%S).tar.gz"
if [ -d "$DATA_DIR" ]; then
    tar -czf "$SAFE_BACKUP" -C "$(dirname $DATA_DIR)" "$(basename $DATA_DIR)" 2>/dev/null || log_warn "当前数据备份失败"
    log_info "  ✓ 安全备份: $SAFE_BACKUP"
fi

# 解压备份文件
log_info "解压备份文件..."
TEMP_DIR=$(mktemp -d)
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# 查找解压后的目录
BACKUP_DATA_DIR=$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)

if [ -z "$BACKUP_DATA_DIR" ]; then
    log_error "备份文件格式错误"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# 恢复永久库
if [ -f "$BACKUP_DATA_DIR/permanent.db" ]; then
    log_info "恢复永久库..."
    cp "$BACKUP_DATA_DIR/permanent.db" "$DATA_DIR/"
    [ -f "$BACKUP_DATA_DIR/permanent.db-wal" ] && cp "$BACKUP_DATA_DIR/permanent.db-wal" "$DATA_DIR/" || true
    [ -f "$BACKUP_DATA_DIR/permanent.db-shm" ] && cp "$BACKUP_DATA_DIR/permanent.db-shm" "$DATA_DIR/" || true
    log_info "  ✓ permanent.db"
fi

# 恢复元信息库
if [ -f "$BACKUP_DATA_DIR/projects_metadata.db" ]; then
    log_info "恢复项目元信息库..."
    cp "$BACKUP_DATA_DIR/projects_metadata.db" "$DATA_DIR/"
    [ -f "$BACKUP_DATA_DIR/projects_metadata.db-wal" ] && cp "$BACKUP_DATA_DIR/projects_metadata.db-wal" "$DATA_DIR/" || true
    [ -f "$BACKUP_DATA_DIR/projects_metadata.db-shm" ] && cp "$BACKUP_DATA_DIR/projects_metadata.db-shm" "$DATA_DIR/" || true
    log_info "  ✓ projects_metadata.db"
fi

# 恢复项目库
if [ -d "$BACKUP_DATA_DIR/projects" ]; then
    log_info "恢复项目数据库..."
    mkdir -p "$DATA_DIR/projects"
    cp -r "$BACKUP_DATA_DIR/projects"/* "$DATA_DIR/projects/"
    project_count=$(find "$DATA_DIR/projects" -name "*.db" -type f | wc -l)
    log_info "  ✓ $project_count 个项目数据库"
fi

# 清理临时文件
rm -rf "$TEMP_DIR"

log_info "恢复完成！"
log_info "如果需要回滚，请使用安全备份: $SAFE_BACKUP"
