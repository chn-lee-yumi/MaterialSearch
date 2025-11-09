# Design: 项目库素材上传改进

## Context

当前系统使用目录扫描方式添加项目素材，用户需要手动输入UNC路径。由于项目素材通常存储在NAS上（如 `\\Daga-nas5\daga-2025-project\...`），且单个项目文件数量较少（10-100个），需要更友好的批量上传体验。

### 约束条件

1. **浏览器安全限制**：Web应用无法通过拖拽获取完整文件路径，只能获取文件名和内容
2. **部署架构**：前端浏览器、后端服务器、NAS三者位于同一局域网，后端可直接访问NAS路径
3. **性能要求**：单个文件最大100MB（PDF），单图最大30MB，单次10-100个文件
4. **存储策略**：仅建立索引，不移动源文件

## Goals / Non-Goals

### Goals
- 提供可视化的文件预览和筛选功能
- 支持路径复制粘贴（混合文件/文件夹）
- 智能识别已索引文件和临时文件
- 优化缩略图加载性能
- 提供清晰的进度反馈

### Non-Goals
- 不支持真正的拖拽操作（受浏览器限制）
- 不改变永久库的上传方式
- 不支持移动端
- 不实现文件移动/复制功能

## Decisions

### Decision 1: 路径解析方案

**选择**：复制粘贴 + 后端路径验证

**理由**：
- 浏览器无法通过拖拽获取UNC路径
- 用户可在资源管理器中使用"Shift+右键→复制为路径"
- 后端可直接访问NAS，无需上传文件内容

**流程**：
```
用户复制路径 → 粘贴到输入框 → 前端解析 → 后端验证和遍历 → 返回文件列表
```

**备选方案**：
- ❌ 方案A：上传文件内容 - 需要传输大量数据，违背"仅索引"原则
- ❌ 方案B：Electron桌面应用 - 增加部署复杂度，不适合多用户协作

---

### Decision 2: 路径解析逻辑

**选择**：前端简单分割 + 后端智能识别

**实现**：
```javascript
// 前端 (static/index.html)
handlePathPaste(text) {
  const lines = text.split('\n')
    .map(line => line.trim().replace(/^"|"$/g, ''))  // 去除引号
    .filter(line => line.length > 0);

  // 发送到后端验证和展开
  axios.post('/api/preview_files', { paths: lines })
}
```

```python
# 后端 (routes.py)
@app.route("/api/preview_files", methods=["POST"])
def preview_files():
    paths = request.json['paths']
    result = []

    for path in paths:
        if os.path.isdir(path):
            # 递归遍历文件夹
            for root, dirs, files in os.walk(path):
                for file in files:
                    full_path = os.path.join(root, file)
                    if is_supported_file(full_path):
                        result.append(get_file_metadata(full_path))
        elif os.path.isfile(path):
            # 单个文件
            if is_supported_file(path):
                result.append(get_file_metadata(path))

    return jsonify(result)
```

**元数据结构**：
```json
{
  "path": "\\\\Daga-nas5\\...\\image.jpg",
  "filename": "image.jpg",
  "size": 2457600,
  "type": "image",
  "ext": ".jpg",
  "mtime": 1640000000,
  "is_indexed": false,
  "phash": "a1b2c3d4e5f6g7h8"
}
```

---

### Decision 3: 缩略图生成策略

**选择**：混合策略（首屏预加载 + 懒加载）

**实现**：
```javascript
// 前端
mounted() {
  // 1. 首屏20个立即请求缩略图
  const firstBatch = this.files.slice(0, 20);
  this.loadThumbnails(firstBatch);

  // 2. 监听滚动事件，懒加载剩余缩略图
  this.$refs.fileList.addEventListener('scroll', this.onScroll);
}

loadThumbnails(files) {
  files.forEach(file => {
    if (!file.thumbnail) {
      axios.get(`/api/thumbnail/${encodeURIComponent(file.path)}`)
        .then(res => file.thumbnail = res.data.url);
    }
  });
}
```

```python
# 后端 (routes.py)
@app.route("/api/thumbnail/<path:file_path>", methods=["GET"])
def get_thumbnail(file_path):
    # 生成缩略图（128x128）
    thumbnail_path = generate_thumbnail(file_path, size=(128, 128))
    return send_file(thumbnail_path)
```

**性能优化**：
- 缩略图缓存在临时目录（`/tmp/thumbnails/`）
- 使用文件路径MD5作为缓存键
- 7天自动清理

**备选方案**：
- ❌ 全部预加载 - 100个文件耗时10-20秒，用户等待时间过长
- ❌ 完全懒加载 - 首屏空白，体验不佳

---

### Decision 4: 重复文件检测

**选择**：phash对比 + 用户决策

**流程**：
```
1. 后端计算新文件的phash
2. 查询数据库是否存在相同phash
3. 如果存在，返回冲突信息
4. 前端显示对比对话框
5. 用户选择：跳过/覆盖/记住选择
```

**对比信息**：
```json
{
  "new_file": {
    "path": "\\\\Daga-nas5\\...\\new.jpg",
    "size": 2457600,
    "mtime": 1640000000,
    "thumbnail": "..."
  },
  "existing_file": {
    "path": "\\\\Daga-nas5\\...\\old.jpg",
    "size": 2450000,
    "mtime": 1635000000,
    "thumbnail": "..."
  }
}
```

**"记住选择"实现**：
```javascript
handleDuplicate(choice) {
  if (this.rememberChoice) {
    this.duplicateStrategy = choice; // 'skip' or 'overwrite'
  }
  // 应用到当前文件
  this.processDuplicate(currentFile, choice);
}
```

---

### Decision 5: 批量索引流程

**选择**：串行处理 + 实时进度反馈

**原因**：
- 避免并发写入数据库冲突
- 便于错误处理和回滚
- 实时反馈用户体验更好

**实现**：
```python
# 后端 (routes.py)
@app.route("/api/batch_index", methods=["POST"])
def batch_index():
    files = request.json['files']
    target = request.json['target']  # 'proj_xxx'
    strategy = request.json.get('duplicate_strategy', 'ask')

    # 使用队列串行化处理
    task_id = str(uuid.uuid4())
    indexing_tasks[task_id] = {
        'total': len(files),
        'processed': 0,
        'success': 0,
        'failed': [],
        'duplicates': []
    }

    # 后台线程处理
    threading.Thread(target=process_batch, args=(task_id, files, target, strategy)).start()

    return jsonify({'task_id': task_id})

# 进度查询
@app.route("/api/batch_index/<task_id>/status", methods=["GET"])
def get_batch_status(task_id):
    return jsonify(indexing_tasks.get(task_id, {}))
```

**前端轮询**：
```javascript
startIndexing() {
  this.indexing = true;
  axios.post('/api/batch_index', { files: this.selectedFiles, target: this.currentLibrary })
    .then(res => {
      this.taskId = res.data.task_id;
      this.pollProgress();
    });
}

pollProgress() {
  const interval = setInterval(() => {
    axios.get(`/api/batch_index/${this.taskId}/status`)
      .then(res => {
        this.progress = res.data;
        if (res.data.processed >= res.data.total) {
          clearInterval(interval);
          this.showReport(res.data);
        }
      });
  }, 500);  // 每500ms查询一次
}
```

---

## Risks / Trade-offs

### Risk 1: 路径格式兼容性

**风险**：不同操作系统路径格式差异（Windows `\\`、Linux `/`）

**缓解措施**：
```python
def normalize_path(path):
    # 统一转换为系统路径
    path = os.path.normpath(path)
    # 确保UNC路径格式正确
    if path.startswith('\\\\'):
        path = path.replace('/', '\\')
    return path
```

### Risk 2: 缩略图生成性能

**风险**：100个文件×200ms = 20秒

**缓解措施**：
- 懒加载策略
- 缓存机制
- 限制并发数（最多5个同时生成）

### Risk 3: 大文件处理

**风险**：100MB的PDF或视频文件可能导致超时

**缓解措施**：
```python
# 大文件检测和警告
if file_size > 50 * 1024 * 1024:  # 50MB
    return {'warning': '文件较大，索引可能需要较长时间'}
```

### Trade-off: 用户体验 vs 性能

**选择**：优先用户体验
- 提供实时进度反馈
- 允许中途取消
- 显示详细的错误信息

**代价**：
- 增加前后端交互次数
- 需要维护任务状态

---

## Migration Plan

### 阶段1：保留现有功能（兼容期）

- 保留原有的扫描对话框（430-458行）
- 新增"添加素材"入口
- 用户可选择使用新旧方式

### 阶段2：灰度测试

- 在项目管理对话框中添加"使用新上传方式"提示
- 收集用户反馈
- 修复bug

### 阶段3：完全切换

- 移除旧的扫描对话框
- 统一使用新的上传方式

### 回滚计划

如果新功能出现严重问题：
1. 隐藏"添加素材"按钮（前端CSS）
2. 恢复显示扫描对话框
3. 后端API保持兼容

---

## Open Questions

1. **是否需要支持视频缩略图？**
   - 当前方案：仅图片有缩略图，视频显示图标
   - 改进方案：视频提取首帧作为缩略图（需要FFmpeg）

2. **历史路径存储位置？**
   - 选项A：localStorage（浏览器本地）
   - 选项B：数据库（多设备同步）
   - 建议：先用localStorage，后续可扩展

3. **是否需要批量标签功能？**
   - 当前：不支持
   - 未来：可在预览界面批量设置标签/描述

4. **错误文件是否需要详细日志？**
   - 当前：显示简单错误信息
   - 改进：可下载详细错误日志
