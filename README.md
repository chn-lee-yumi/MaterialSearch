# MaterialSearch 本地素材搜索

[**中文**](./README.md) | [**English**](./README_EN.md)

扫描本地的图片以及视频，并且可以用自然语言进行查找。

## 功能

- 文字搜图
- 以图搜图
- 文字搜视频（会给出符合描述的视频片段）
- 以图搜视频（通过视频截图搜索所在片段）
- 图文相似度计算（只是给出一个分数，用处不大）

## 使用说明

### 通过源码部署

首先安装Python环境，然后下载本仓库代码。

注意，首次运行会自动下载模型。下载速度可能比较慢，请耐心等待。如果网络不好，模型可能会下载失败，这个时候重新执行程序即可。

1. 首次使用前需要安装依赖：`pip install -U -r requirements.txt`，Windows系统可以双击`install.bat`（NVIDIA GPU加速）或`install_cpu.bat`（纯CPU）。
2. 如果你打算使用GPU加速，则执行基准测试判断是CPU快还是GPU快：`python benchmark.py`，Windows系统可以双击`benchmark.bat`。GPU不一定比CPU快，在我的Mac上CPU更快。
3. 如果不是CPU最快，则修改配置中的`DEVICE`和`DEVICE_TEXT`，改为对应设备（配置修改方法请参考后面的配置说明）。
4. 启动程序：`python main.py`，Windows系统可以双击`run.bat`。

如遇到`requirements.txt`版本依赖问题（比如某个库版本过新会导致运行报错），请提issue反馈，我会添加版本范围限制。

如遇到硬件支持但无法使用GPU加速的情况，请根据[PyTorch文档](https://pytorch.org/get-started/locally/)更新torch版本。

如果想使用"下载视频片段"的功能，需要安装`ffmpeg`。如果是Windows系统，记得把`ffmpeg.exe`所在目录加入环境变量`PATH`，可以参考：[Bing搜索](https://cn.bing.com/search?q=windows+%E5%A6%82%E4%BD%95%E6%B7%BB%E5%8A%A0+path+%E7%8E%AF%E5%A2%83%E5%8F%98%E9%87%8F)。

### 通过Docker部署

目前只有一个Docker镜像，支持`amd64`和`arm64`，打包了默认模型（`openai/clip-vit-base-patch32`和`IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese`）并且支持GPU（仅`amd64`架构的镜像支持）。 如有更多需求欢迎提issue。

启动镜像前，你需要准备：

1. 数据库的保存路径
2. 你的扫描路径以及打算挂载到容器内的哪个路径
3. 根据你的路径信息，准备一个`config.py`
4. 根据你的路径信息，修改`docker-compose.yml`里面的`volume`路径
5. 如果打算使用GPU，则需要取消注释`docker-compose.yml`里面的对应部分

具体请参考`docker-compose.yml`，已经写了详细注释。

最后执行`docker-compose up -d`启动容器即可。

注意：不推荐对容器设置内存限制，否则可能会出现奇怪的问题。比如[这个issue](https://github.com/chn-lee-yumi/MaterialSearch/issues/6)。

## 配置说明

所有配置都在`config.py`文件中，里面已经写了详细的注释。

建议通过环境变量或在项目根目录创建`.env`文件修改配置。如果没有配置对应的变量，则会使用`config.py`中的默认值。例如`os.getenv('HOST', '0.0.0.0')`，如果没有配置`HOST`变量，则`HOST`默认为`0.0.0.0`。

`.env`文件配置示例：

```
ASSETS_PATH=C:/Users/Administrator/Documents,C:/Users/Administrator/Pictures
DEVICE=cuda
DEVICE_TEXT=cuda
```

目前功能仍在迭代中，配置会经常变化。如果更新版本后发现无法启动，需要参考最新的配置文件手动改一下配置。

如果你发现某些格式的图片或视频没有被扫描到，可以尝试在`IMAGE_EXTENSIONS`和`VIDEO_EXTENSIONS`增加对应的后缀。如果你发现一些支持的后缀没有被添加到代码中，欢迎提issue或pr增加。

小图片没被扫描到的话，可以调低`IMAGE_MIN_WIDTH`和`IMAGE_MIN_HEIGHT`重试。

## 问题解答

如遇问题，请先仔细阅读本文档。如果找不到答案，请在issue中搜索是否有类似问题。如果没有，可以新开一个issue，**详细说明你遇到的问题，加上你做过的尝试和思考，附上报错内容和截图，并说明你使用的系统（Windows/Linux/MacOS）和`config.py`的配置**。

本人只负责本项目的功能、代码和文档等相关问题（例如功能不正常、代码报错、文档内容有误等）。**运行环境问题请自行解决（例如：如何配置Python环境，无法使用GPU加速，如何安装ffmpeg等）。**

本人做此项目纯属“为爱发电”（也就是说，其实本人并没有义务解答你的问题）。为了提高问题解决效率，请尽量在开issue时一次性提供尽可能多的信息。如问题已解决，请记得关闭issue。一个星期无人回复的issue会被关闭。如果在被回复前已自行解决问题，推荐留下解决步骤，赠人玫瑰，手有余香。

## 硬件要求

推荐使用`amd64`或`arm64`架构的CPU。内存最低2G，但推荐最少4G内存。如果照片数量很多，推荐增加更多内存。

测试环境：J3455，8G内存。全志H6，2G内存。

如果使用AMD的GPU，仅支持在Linux下使用GPU加速。请参考：[PyTorch文档](https://pytorch.org/get-started/locally/)。

## 搜索速度

在 J3455 CPU 上，1秒钟可以进行大约17000次图片匹配（视频匹配可能会稍慢一些）。

## 已知问题

1. 部分图片和视频无法在网页上显示，原因是浏览器不支持这一类型的文件（例如tiff文件，svq3编码的视频等）。

## 关于PR

欢迎提PR！不过为了避免无意义的劳动，建议先提issue讨论一下。

提PR前请确保代码已经格式化。
