# 项目 上下文

## 目的
MaterialSearch 是一个基于 AI 的本地素材搜索系统，允许用户通过自然语言或图片来搜索本地存储的图片和视频。

**核心功能：**
- 文本搜图：通过描述性文字搜索相关图片
- 以图搜图：通过上传图片找到相似图片
- 文本搜视频：根据描述找到匹配的视频片段
- 以图搜视频：通过截图找到对应的视频段落
- 图文相似度计算：提供量化的相似度评分

**项目定位：**
这是从开源项目分叉的二次开发版本，原项目地址：https://github.com/chn-lee-yumi/MaterialSearch
本仓库用于个人定制化开发和功能增强，暂不向上游提交。

## 技术栈

### 后端框架
- **Python 3.9+**：主要开发语言
- **Flask 2.2.2+**：Web 框架，处理 HTTP 请求和路由
- **SQLAlchemy 2.0.20+**：ORM 框架，管理数据库操作

### AI/机器学习
- **PyTorch 2.0+**：深度学习框架
- **Transformers 4.28.1+**：HuggingFace 模型库，加载 CLIP 模型
- **CLIP 模型**：默认使用 `OFA-Sys/chinese-clip-vit-base-patch16`（中文小模型）
- **FAISS**：Facebook 的向量相似度搜索库，用于高效检索
- **Accelerate 1.5.0+**：模型加速库

### 图像/视频处理
- **Pillow 8.1.0+**：图像处理基础库
- **pillow-heif 0.14.0+**：HEIC 格式图片支持
- **opencv-python-headless 4.7.0+**：视频帧提取和处理
- **FFmpeg**：视频片段下载功能（外部依赖）

### 前端
- **原生 HTML/CSS/JavaScript**：静态页面，无前端框架
- 位于 `static/` 目录

### 部署
- **Docker**：支持容器化部署（仅 amd64 架构）
- **python-dotenv**：环境变量管理

## 项目约定

### 代码风格
- **语言规范**：遵循 PEP 8 Python 代码规范
- **命名约定**：
  - 变量/函数：snake_case（如 `scan_process_batch_size`）
  - 常量：UPPER_CASE（如 `HOST`, `PORT`）
  - 类名：PascalCase（如需定义）
- **配置管理**：所有配置集中在 `config.py`，通过环境变量或 `.env` 文件覆盖
- **注释**：配置文件中使用中文注释，代码中优先使用清晰的命名减少注释需求

### 架构模式
- **MVC 架构**：
  - Models: `models.py` - 数据库模型定义
  - Views/Routes: `routes.py` - API 路由和业务逻辑
  - Controllers: 各模块文件（`search.py`, `scan.py`, `database.py`）
- **模块职责分离**：
  - `main.py`：应用入口
  - `config.py`：配置管理
  - `database.py`：数据库操作
  - `search.py`：搜索逻辑
  - `scan.py`：素材扫描和特征提取
  - `process_assets.py`：素材处理工具
  - `utils.py`：工具函数
- **缓存策略**：搜索结果在内存中缓存（LRU），可配置缓存大小

### 测试策略
- **当前状态**：项目包含 `api_test.py` 和 `benchmark.py` 用于基础测试
- **测试方针**：
  - 功能变更前应通过现有测试
  - 新增功能建议添加对应的测试用例
  - 重点测试：模型推理、向量检索、数据库操作

### Git 工作流
- **分支策略**：
  - `main`：稳定基线分支，与远程仓库同步
  - `dev`：**主开发分支**，所有日常开发在此进行
  - 功能分支：如需要可从 dev 创建临时分支
- **提交规范**：
  - 使用清晰的中文或英文描述提交内容
  - 提交前确保代码可运行
  - 避免提交敏感信息（`.env` 文件已在 `.gitignore`）
- **同步策略**：
  - 定期推送 dev 分支到个人远程仓库
  - 暂不向上游（原作者）提交 PR
  - 如需同步上游更新，从原仓库拉取到 main，再合并到 dev

## 领域上下文

### AI 模型相关
- **CLIP（Contrastive Language-Image Pre-training）**：
  - OpenAI 开发的多模态模型，能同时理解图像和文本
  - 通过对比学习将图像和文本映射到同一向量空间
  - 本项目使用的是中文版 CLIP（chinese-clip）
- **向量检索（Vector Search）**：
  - 将图片和文本转换为高维向量（embeddings）
  - 通过 FAISS 进行高效的最近邻搜索
  - 余弦相似度计算匹配程度
- **模型切换影响**：更换模型需要删除数据库并重新扫描所有素材

### 素材管理
- **扫描流程**：遍历指定目录 → 过滤文件 → 提取特征 → 存入数据库
- **视频处理**：按固定时间间隔（默认 2 秒）提取关键帧，每帧单独索引
- **缩略图**：自动生成小图用于前端快速展示
- **增量更新**：支持检测文件变化，仅处理新增/修改的素材

### 用户使用场景
- **设计师素材管理**：快速找到项目所需的参考图片
- **视频内容检索**：在大量视频素材中定位特定场景
- **灵感查找**：通过模糊描述找到相关视觉素材

## 重要约束

### 技术约束
- **Python 版本**：需要 3.9 或更高版本
- **内存要求**：最低 2GB，推荐 4GB+（取决于素材数量）
- **GPU 支持**：可选，但使用 GPU 能显著提升扫描速度
  - 4G 显存：小模型 + SCAN_PROCESS_BATCH_SIZE=6
  - 8G 显存：小模型 + SCAN_PROCESS_BATCH_SIZE=12
- **架构限制**：
  - Docker 镜像仅支持 amd64
  - 推荐使用 amd64 或 arm64 CPU
- **浏览器兼容性**：某些视频编码（如 SVQ3）和图片格式（如 TIFF）可能无法在浏览器中直接显示

### 性能约束
- **搜索速度**：J3455 CPU 测试环境下每秒可匹配 31,000 张图片或 25,000 视频帧
- **扫描速度**：不建议设置 ASSETS_PATH 为远程目录（SMB/NFS），会显著降低扫描速度
- **视频展示限制**：建议单次搜索不超过 12 个视频结果，避免浏览器卡顿

### 法律/许可约束
- **开源许可**：GNU General Public License v3.0 (GPLv3)
- **代码混淆说明**：部分源码（`routes_encrypted.py`）已混淆以保护原作者版权
- **使用要求**：必须保留原作者署名信息
- **贡献鼓励**：如有改进，欢迎通过 PR 回馈社区

### 业务约束
- **离线优先**：设计为本地部署，保护用户隐私
- **模型下载**：首次运行需联网下载模型（约几百 MB）
- **数据隔离**：数据库和索引完全在本地，不上传任何素材

## 外部依赖

### AI 模型服务
- **HuggingFace Hub**：模型下载来源
  - 默认模型：`OFA-Sys/chinese-clip-vit-base-patch16`
  - 可切换其他 CLIP 模型（中文大/超大模型，英文模型等）
  - Docker 环境默认设置 `TRANSFORMERS_OFFLINE=1`，跳过版本检查
  - 国内用户可能需要配置代理（`http_proxy`, `https_proxy`）

### 系统工具
- **FFmpeg**：
  - 用途：视频片段下载功能
  - 安装：Windows 可运行 `install_ffmpeg.bat`
  - 可选：不安装不影响搜索功能

### Docker 镜像仓库
- **DockerHub**：`yumilee/materialsearch`
- **阿里云**：`registry.cn-hongkong.aliyuncs.com/chn-lee-yumi/materialsearch`（国内推荐）

### 运行时依赖
- **CUDA**（可选）：GPU 加速需要 NVIDIA 驱动和 CUDA 工具包
- **操作系统**：Windows/Linux/MacOS 均支持

### 开发依赖
- **requirements.txt**：生产环境依赖（CPU 版本）
- **requirements_windows.txt**：Windows 特定依赖
