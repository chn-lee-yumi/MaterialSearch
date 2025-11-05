# Design: 项目数据库架构技术设计

## Context

### 背景
MaterialSearch 原始设计是个人用户本地使用，单一数据库存储所有图片。现在需要适配建筑设计团队的协作场景，核心需求是"临时项目文件"与"永久精选素材"分离管理。

### 约束条件
1. **部署环境**：20 人团队，Linux 服务器，图片存储在群辉 NAS
2. **技术能力**：团队无编程人员，依赖 AI Agent 维护，必须开箱即用
3. **数据量**：年均 50 项目 × 100 张/项目 = 5000 张/年，永久库约 1 万张
4. **使用模式**：项目内搜索为主，极少跨项目搜索
5. **NAS 限制**：SQLite 不能直接放 NAS（文件锁问题），需数据库在本地、图片在 NAS

### 利益相关者
- **终端用户**：建筑设计师，需要快速检索项目素材和参考图片
- **系统管理员**：通过 AI Agent 维护系统，需要简单可靠的方案
- **未来扩展**：可能迁移到 PostgreSQL，需预留迁移路径

## Goals / Non-Goals

### Goals
1. **架构目标**：实现永久库和项目库物理隔离
2. **性能目标**：项目内搜索 < 1 秒，永久库搜索 < 3 秒
3. **易用性目标**：项目归档流程清晰，操作简单
4. **可靠性目标**：自动备份，数据零丢失
5. **扩展性目标**：未来可平滑迁移到 PostgreSQL

### Non-Goals
- ❌ 不实现细粒度权限控制（当前所有人权限相同）
- ❌ 不优化跨项目全局搜索（用户很少使用）
- ❌ 不支持图片文件移动（文件路径保持不变）
- ❌ 不实现实时同步（定时备份即可）

## Decisions

### 决策 1：多库架构 vs 单库架构

**选择：多库架构（每项目一个 SQLite 文件）**

#### 对比分析

| 维度 | 单库 + project_id | 多库（每项目独立） | 胜出 |
|------|------------------|-------------------|------|
| 项目内搜索 | 需过滤 6 万条记录 | 仅扫描 100 条 | **多库** |
| 永久库搜索 | 扫描 1 万条 | 扫描 1 万条 | 平手 |
| 全局搜索 | 一次查询 | 需打开多个文件 | 单库 |
| 写入性能 | 所有项目竞争同一锁 | 项目间无竞争 | **多库** |
| 项目归档 | UPDATE + INSERT | 复制记录 | 平手 |
| 项目删除 | 软删除或物理删除 | 直接删除文件 | **多库** |
| 备份恢复 | 全量备份 | 按项目备份 | **多库** |
| 管理复杂度 | 简单 | 略复杂 | 单库 |
| 数据库大小 | 单个大文件 | 多个小文件 | 平手 |

#### 决策理由
1. **用户场景主导**：95% 的搜索是项目内搜索，多库架构直接匹配使用场景
2. **性能优势明显**：100 条 vs 6 万条，速度提升 600 倍
3. **隔离性好**：项目数据库损坏不影响其他项目
4. **生命周期清晰**：项目完成后直接删除 .db 文件

#### 备选方案
**单库 + 分区表**（PostgreSQL 支持）：
- 优点：单一数据库连接，查询简单
- 缺点：需要 PostgreSQL，与"开箱即用"目标冲突
- 结论：未来迁移到 PostgreSQL 时可考虑

---

### 决策 2：数据库存储位置

**选择：数据库在服务器本地磁盘，图片在 NAS**

#### 技术原因
SQLite 在网络文件系统（NFS/SMB）上存在文件锁不可靠问题：
- 多人并发写入 → 锁失效 → **数据库损坏风险**
- 网络延迟 → 事务超时 → 写入失败

参考：[SQLite FAQ - Network File Systems](https://www.sqlite.org/faq.html#q5)

#### 架构方案
```
服务器本地磁盘：
  └─ /var/lib/materialsearch/
     ├─ permanent.db              (约 20MB)
     ├─ projects_metadata.db      (约 1MB)
     └─ projects/
        ├─ proj_2025_万科_01.db  (约 2MB)
        └─ proj_2025_万科_02.db

NAS（网络挂载到 /mnt/nas）：
  └─ /mnt/nas/
     ├─ 永久素材库/              (实际图片文件)
     └─ 项目文件/
        └─ 2025_万科_01/
```

#### 优点
- ✅ 避免文件锁问题
- ✅ 数据库文件小，备份快
- ✅ 图片文件路径不变（用户要求）
- ✅ NAS 断连只影响图片显示，不影响搜索

---

### 决策 3：Schema 扩展策略

**选择：显式字段 + JSON 字段混合**

#### 设计原则
- **高频查询字段**：显式字段 + 索引（如 `category`、`aspect_ratio`）
- **低频或灵活字段**：JSON 字段（如 `tags`）
- **预留扩展字段**：AI 相关字段先定义，值可为 NULL

#### 示例
```sql
-- 显式字段（需要索引和过滤）
category TEXT,                     -- 高频：分类筛选
aspect_ratio REAL,                 -- 高频：自动排版
width INTEGER, height INTEGER,     -- 高频：尺寸筛选

-- JSON 字段（灵活扩展）
tags TEXT,                         -- JSON: ["标签1", "标签2"]

-- 预留字段（未来功能）
ai_description TEXT,               -- AI 图片描述（后续实现）
ai_description_vector BLOB,        -- 描述向量（后续实现）
phash TEXT,                        -- 感知哈希（去重功能用）
```

#### 索引策略
```sql
-- 单列索引（常用过滤）
CREATE INDEX idx_category ON image(category);
CREATE INDEX idx_aspect_ratio ON image(aspect_ratio);

-- 复合索引（组合查询）
CREATE INDEX idx_category_style ON image(category, design_style);
CREATE INDEX idx_aspect_category ON image(aspect_ratio_standard, category);
```

#### SQLite 限制
- SQLite 不支持部分索引（PostgreSQL 的 `WHERE` 子句）
- 不支持表达式索引（如 `CREATE INDEX ON (width/height)`）
- JSON 函数支持有限（3.38+ 支持基本操作）

**解决方案**：预计算字段（如 `aspect_ratio`）而非运行时计算。

---

### 决策 4：归档流程设计

**选择：记录级复制 + 标记**

#### 流程设计
```
用户操作：选择项目中的图片 → 点击"归档到永久库"
    ↓
1. 从项目库读取记录（包括向量特征）
    ↓
2. 插入永久库
   - 复制所有字段
   - 设置 source_type = 'project_archive'
   - 设置 source_project = 'proj_2025_万科_01'
    ↓
3. 更新项目库记录
   - archived = 1
   - archived_to_id = <永久库中的新ID>
   - archived_time = NOW()
    ↓
4. 返回成功，前端提示
```

#### 关键点
- **向量不重新计算**：直接复制 `features` BLOB 数据，节省 CPU
- **文件路径不变**：NAS 上的图片不移动
- **可追溯**：永久库记录保留来源项目信息
- **可选删除**：用户可选择归档后是否从项目库删除

#### 代码示例
```python
def archive_images(project_id, image_ids):
    """归档图片到永久库"""
    project_db = get_project_db(project_id)
    permanent_db = get_permanent_db()

    # 1. 读取项目库记录
    images = project_db.query(Image).filter(Image.id.in_(image_ids)).all()

    # 2. 插入永久库
    for img in images:
        new_img = Image(
            path=img.path,
            features=img.features,  # 直接复制向量
            width=img.width,
            height=img.height,
            # ... 其他字段
            source_type='project_archive',
            source_project=project_id
        )
        permanent_db.add(new_img)
        permanent_db.flush()  # 获取新 ID

        # 3. 标记项目库记录
        img.archived = True
        img.archived_to_id = new_img.id
        img.archived_time = datetime.now()

    permanent_db.commit()
    project_db.commit()
```

---

### 决策 5：并发控制策略

**选择：队列串行化 + WAL 模式**

#### 问题分析
SQLite 的并发限制：
- 同一时刻只允许一个写事务
- 读写互斥（普通模式）

#### 解决方案

**1. 启用 WAL 模式（Write-Ahead Logging）**
```python
# 数据库初始化时
conn.execute("PRAGMA journal_mode=WAL")
```

好处：
- 读写不互斥（写不阻塞读）
- 多个读可以并发
- 性能提升 20-30%

**2. 上传队列串行化**
```python
import queue
import threading

upload_queue = queue.Queue()

def upload_worker():
    """后台线程处理上传"""
    while True:
        task = upload_queue.get()
        try:
            process_upload(task)  # 向量化 + 入库
        finally:
            upload_queue.task_done()

# 启动后台线程
threading.Thread(target=upload_worker, daemon=True).start()
```

好处：
- 保证串行写入，无并发冲突
- 用户上传立即返回，异步处理
- 队列积压时自动排队

#### 超时配置
```python
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30  # 等待锁超时时间（秒）
    }
)
```

---

### 决策 6：备份策略

**选择：文件级增量备份 + 定时任务**

#### 备份方案
```bash
#!/bin/bash
# /opt/materialsearch/backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/materialsearch"
DATA_DIR="/var/lib/materialsearch"

# 创建今日备份目录
mkdir -p "$BACKUP_DIR/$DATE"

# 备份永久库
cp "$DATA_DIR/permanent.db" "$BACKUP_DIR/$DATE/"
cp "$DATA_DIR/permanent.db-wal" "$BACKUP_DIR/$DATE/" 2>/dev/null || true
cp "$DATA_DIR/permanent.db-shm" "$BACKUP_DIR/$DATE/" 2>/dev/null || true

# 备份项目元信息
cp "$DATA_DIR/projects_metadata.db" "$BACKUP_DIR/$DATE/"

# 备份所有项目库
cp -r "$DATA_DIR/projects" "$BACKUP_DIR/$DATE/"

# 压缩
tar -czf "$BACKUP_DIR/$DATE.tar.gz" -C "$BACKUP_DIR" "$DATE"
rm -rf "$BACKUP_DIR/$DATE"

# 清理 30 天前的备份
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete

# 记录日志
echo "[$(date)] Backup completed: $DATE.tar.gz" >> /var/log/materialsearch_backup.log
```

#### Cron 配置
```bash
# 每天凌晨 3 点备份
0 3 * * * /opt/materialsearch/backup.sh
```

#### 恢复流程
```bash
# 1. 停止服务
systemctl stop materialsearch

# 2. 恢复数据
tar -xzf /backup/materialsearch/20250115_030000.tar.gz -C /var/lib/materialsearch

# 3. 重启服务
systemctl start materialsearch
```

---

## Risks / Trade-offs

### 风险 1：多库管理复杂度
**风险**：项目数增加后，管理 50+ 数据库文件
**缓解**：
- 项目元信息库统一管理
- 提供项目列表 API
- 归档后的项目可自动清理

### 风险 2：全局搜索性能
**风险**：全局搜索需打开所有项目库，可能较慢
**缓解**：
- 用户很少使用全局搜索（95% 是项目内搜索）
- 可限制全局搜索的项目数量（如最近 10 个项目）
- 未来迁移到 PostgreSQL 自然解决

### 风险 3：WAL 文件清理
**风险**：WAL 模式产生 -wal 和 -shm 文件，可能误删
**缓解**：
- 文档明确说明不可手动删除 WAL 文件
- 备份脚本自动包含 WAL 文件
- SQLite 会自动清理（checkpoint）

### Trade-off 1：灵活性 vs 性能
**决策**：优先性能
- 使用显式字段而非全 JSON（查询更快）
- 预计算字段（如宽高比）而非运行时计算
- 代价：Schema 变更需要 ALTER TABLE

### Trade-off 2：简单性 vs 扩展性
**决策**：平衡
- 当前使用 SQLite（简单）
- Schema 设计兼容 PostgreSQL（扩展性）
- 预留 AI 字段（未来功能）

---

## Migration Plan

### 阶段 1：Schema 迁移（自动化脚本）

```python
def migrate_existing_database():
    """迁移现有数据库到新 Schema"""
    # 1. 备份
    backup_database()

    # 2. 添加新字段
    alter_commands = [
        "ALTER TABLE image ADD COLUMN width INTEGER",
        "ALTER TABLE image ADD COLUMN height INTEGER",
        "ALTER TABLE image ADD COLUMN aspect_ratio REAL",
        "ALTER TABLE image ADD COLUMN aspect_ratio_standard TEXT",
        "ALTER TABLE image ADD COLUMN file_size INTEGER",
        "ALTER TABLE image ADD COLUMN file_format TEXT",
        "ALTER TABLE image ADD COLUMN upload_time DATETIME DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE image ADD COLUMN category TEXT",
        "ALTER TABLE image ADD COLUMN tags TEXT",
        "ALTER TABLE image ADD COLUMN is_deleted BOOLEAN DEFAULT 0",
        # ... 其他字段
    ]

    for cmd in alter_commands:
        try:
            db.execute(cmd)
        except Exception as e:
            logging.error(f"Migration failed: {cmd}, {e}")
            rollback()
            raise

    # 3. 计算现有图片的属性
    images = db.query(Image).all()
    for img in images:
        try:
            pil_img = PILImage.open(img.path)
            img.width, img.height = pil_img.size
            img.aspect_ratio = round(img.width / img.height, 3)
            img.aspect_ratio_standard = get_standard_aspect_ratio(img.aspect_ratio)
            img.file_size = os.path.getsize(img.path)
            img.file_format = pil_img.format.lower()
        except:
            logging.warning(f"Cannot read image: {img.path}")

    db.commit()

    # 4. 创建索引
    create_indexes()
```

### 阶段 2：数据验证
- 检查所有字段是否正确填充
- 验证宽高比计算准确性
- 测试搜索功能

### 阶段 3：逐步部署
1. 测试环境验证（用户测试数据）
2. 生产环境备份
3. 执行迁移脚本
4. 验证功能
5. 监控一周

### 回滚计划
```python
def rollback_migration():
    """回滚到备份"""
    # 1. 停止服务
    stop_service()

    # 2. 恢复备份
    restore_from_backup()

    # 3. 重启旧版本服务
    start_old_version()
```

---

## Open Questions

### 已解决
- ✅ 单库 vs 多库：选择多库
- ✅ 数据库存储位置：服务器本地磁盘
- ✅ 图片存储位置：保持 NAS
- ✅ 归档流程：记录级复制
- ✅ 项目创建方式：手动创建
- ✅ 项目完成后：数据库保留，可手动删除

### 待讨论
- ⏳ 是否需要项目标签系统？（用于快速筛选项目）
- ⏳ 是否需要项目模板？（创建项目时选择"住宅/商业/办公"）
- ⏳ 全局搜索是否限制项目数量？（如只搜最近 10 个活跃项目）

---

## Future Considerations

### PostgreSQL 迁移路径
当数据量增长到 10 万+ 或需要更强的并发能力时：

1. **Schema 映射**
```sql
-- PostgreSQL Schema（几乎相同）
CREATE TABLE image (
    id SERIAL PRIMARY KEY,           -- AUTOINCREMENT → SERIAL
    project_id TEXT,                 -- 新增：项目标识
    path TEXT NOT NULL,
    features BYTEA NOT NULL,         -- BLOB → BYTEA
    aspect_ratio REAL,
    tags JSONB,                      -- TEXT → JSONB（原生支持）
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ...
);

-- 向量索引（pgvector 扩展）
CREATE EXTENSION vector;
ALTER TABLE image ADD COLUMN features_vector vector(512);
CREATE INDEX idx_features ON image USING ivfflat (features_vector);
```

2. **迁移脚本**
```python
def migrate_to_postgresql():
    sqlite_dbs = [
        ('permanent.db', None),
        *[(f, extract_project_id(f)) for f in glob.glob('projects/proj_*.db')]
    ]

    for db_file, project_id in sqlite_dbs:
        migrate_database(db_file, project_id, pg_conn)
```

3. **优势**
- 真正的并发写入
- 原生 JSON 支持
- pgvector 向量索引（100 倍加速）
- 分区表（按项目分区）

---

## References

- [SQLite FAQ - Locking And Concurrency](https://www.sqlite.org/faq.html)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)
- [PostgreSQL pgvector Extension](https://github.com/pgvector/pgvector)
- [CLIP Model Architecture](https://github.com/openai/CLIP)
