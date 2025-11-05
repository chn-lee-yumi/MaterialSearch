#!/bin/bash
#
# 数据库备份脚本
# 备份永久库、元信息库和所有项目数据库
#

set -e

# 配置
DATA_DIR="${DATA_DIR:-./instance}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DATE=$(date +%Y%m%d_%H%M%S)

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

# 创建备份目录
mkdir -p "$BACKUP_DIR/$DATE"

log_info "开始备份..."
log_info "  数据目录: $DATA_DIR"
log_info "  备份目录: $BACKUP_DIR/$DATE"

# 备份永久库
if [ -f "$DATA_DIR/permanent.db" ]; then
    log_info "备份永久库..."
    cp "$DATA_DIR/permanent.db" "$BACKUP_DIR/$DATE/"
    [ -f "$DATA_DIR/permanent.db-wal" ] && cp "$DATA_DIR/permanent.db-wal" "$BACKUP_DIR/$DATE/" 2>/dev/null || true
    [ -f "$DATA_DIR/permanent.db-shm" ] && cp "$DATA_DIR/permanent.db-shm" "$BACKUP_DIR/$DATE/" 2>/dev/null || true
    log_info "  ✓ permanent.db"
else
    log_warn "  永久库不存在: $DATA_DIR/permanent.db"
fi

# 备份项目元信息库
if [ -f "$DATA_DIR/projects_metadata.db" ]; then
    log_info "备份项目元信息库..."
    cp "$DATA_DIR/projects_metadata.db" "$BACKUP_DIR/$DATE/"
    [ -f "$DATA_DIR/projects_metadata.db-wal" ] && cp "$DATA_DIR/projects_metadata.db-wal" "$BACKUP_DIR/$DATE/" 2>/dev/null || true
    [ -f "$DATA_DIR/projects_metadata.db-shm" ] && cp "$DATA_DIR/projects_metadata.db-shm" "$BACKUP_DIR/$DATE/" 2>/dev/null || true
    log_info "  ✓ projects_metadata.db"
else
    log_warn "  元信息库不存在: $DATA_DIR/projects_metadata.db"
fi

# 备份所有项目库
if [ -d "$DATA_DIR/projects" ]; then
    log_info "备份项目数据库..."
    project_count=$(find "$DATA_DIR/projects" -name "*.db" -type f | wc -l)
    if [ $project_count -gt 0 ]; then
        cp -r "$DATA_DIR/projects" "$BACKUP_DIR/$DATE/"
        log_info "  ✓ $project_count 个项目数据库"
    else
        log_warn "  没有找到项目数据库"
    fi
else
    log_warn "  项目目录不存在: $DATA_DIR/projects"
fi

# 压缩备份
log_info "压缩备份文件..."
cd "$BACKUP_DIR"
tar -czf "$DATE.tar.gz" "$DATE"
backup_size=$(du -h "$DATE.tar.gz" | cut -f1)
log_info "  ✓ 备份大小: $backup_size"

# 删除临时目录
rm -rf "$DATE"

# 清理旧备份
log_info "清理 $RETENTION_DAYS 天前的旧备份..."
old_backups=$(find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS)
if [ -n "$old_backups" ]; then
    deleted_count=$(echo "$old_backups" | wc -l)
    echo "$old_backups" | xargs rm -f
    log_info "  ✓ 删除 $deleted_count 个旧备份"
else
    log_info "  没有需要清理的旧备份"
fi

# 记录日志
log_file="$BACKUP_DIR/backup.log"
echo "[$(date)] 备份完成: $DATE.tar.gz ($backup_size)" >> "$log_file"

log_info "备份完成！"
log_info "  备份文件: $BACKUP_DIR/$DATE.tar.gz"
