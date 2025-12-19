# MaterialSearch

[**中文**](./README_ZH.md) | [**English**](./README.md)

Search local photos and videos through natural language.

This repository now contains only the front-end code of the project. The core logic has been separated into a standalone pip package, which is hosted in another repository: [materialsearch-core](https://github.com/chn-lee-yumi/MaterialSearch-core). This structure makes version control and distribution easier, and also allows developers to use the core functions directly in their own projects.

Some parts of the source code in this repository have been intentionally obfuscated. In the past, there were incidents where individuals maliciously removed or altered copyright and attribution information, which caused negative impact to the project. The obfuscation is solely for protecting authorship and legal integrity, and does **not** restrict any legitimate usage permitted under the GNU General Public License v3.0 (GPLv3).

We kindly ask users to respect the original work and keep all relevant notices.

If you make useful changes to the project (bug fixes, feature additions, etc.), you are welcome to contribute back through a pull request so that others can benefit.

If you would like to contribute:
- Frontend features: please submit a PR in this repository.
- API-related requests: please submit an issue in this repository (the API implementation is not open-source and is maintained by the author).
- Other features: please submit an issue here or a PR to the [materialsearch-core](https://github.com/chn-lee-yumi/MaterialSearch-core) repository.

Note: AI-generated code contributions are not accepted. Please ensure that any submitted code is written and understood by yourself.

## Features

- Text-based image search
- Image-based image search
- Text-based video search (provides matching video clips based on descriptions)
- Image-based video search (searches for video segments based on screenshots)
- Calculation of image-text similarity (provides a score, not very useful)

## Deploy Instructions

### Windows Bundle

Note: The minimum supported system is Windows 10.
If you are still using Windows 7, please upgrade your system or switch to a newer computer.

Tutorial video on Bilibili (Chinese):
[Click here](https://www.bilibili.com/video/BV1SoqbB4Ehw/)

User support QQ group (Chinese, community-driven): **1029566498**
(The author has limited time, so the group is mainly for users to help each other.)

First, download the bundle and extract it using **[7-Zip](https://www.7-zip.org/)**.
Using other extraction tools may cause errors.

There are two versions of the bundle:

* `MaterialSearchWindows.7z`: does *not* include the model. Suitable for advanced users.
* `MaterialSearchWindows_include_base_model.7z`: includes the base model (`OFA-Sys/chinese-clip-vit-base-patch16`) and works out of the box. **Recommended for most users.**

Download links:

* GitHub Release
  [https://github.com/chn-lee-yumi/MaterialSearch/releases/latest](https://github.com/chn-lee-yumi/MaterialSearch/releases/latest)
* Quark Cloud
  [https://pan.quark.cn/s/ae137c439484](https://pan.quark.cn/s/ae137c439484)
* Baidu Cloud
  [https://pan.baidu.com/s/1uQ8t-4mbYmcfi6FjwzdrrQ](https://pan.baidu.com/s/1uQ8t-4mbYmcfi6FjwzdrrQ) (code: CHNL)

After extracting, please read the included `使用说明.txt` (Chinese) file.
The bundle will automatically choose between integrated or dedicated GPU for acceleration.

### Deployment via Docker

Supports `amd64` architectures. It includes the base models (`OFA-Sys/chinese-clip-vit-base-patch16`) and supports GPU acceleration.

Image repositories:
- [yumilee/materialsearch](https://hub.docker.com/r/yumilee/materialsearch) (DockerHub)
- registry.cn-hongkong.aliyuncs.com/chn-lee-yumi/materialsearch (Aliyun, recommended for users in Mainland China)

Before starting the image, you need to prepare:

1. The path to save the database
2. The scan paths on your local machine and the paths to be mounted inside the container
3. You can configure through modifying the `environment` and `volumes` sections in the `docker-compose.yml` file
4. If you plan to use GPU acceleration, uncomment the corresponding section in the `docker-compose.yml` file

Please refer to the `docker-compose.yml` file for details, as it contains detailed comments.

Finally, execute `docker-compose up -d` to start the container.

Note:
- It is not recommended to set memory limits for the container, as it may cause strange issues. For example, refer to [this issue](https://github.com/chn-lee-yumi/MaterialSearch/issues/6).
- Docker image has the default environment variables `TRANSFORMERS_OFFLINE=1`, which means it won't connect to huggingface to check the model version. If you want to change the default model in the container, you have to modify `.env` and set `TRANSFORMERS_OFFLINE=0`.

## Configuration Instructions

All configurations are in the [`config.py` file](https://github.com/chn-lee-yumi/MaterialSearch-core/blob/main/src/materialsearch_core/config.py), which contains detailed comments.

It is recommended to modify the configuration through environment variables or by creating a `.env` file in the project root directory. If a corresponding variable is not configured, the default value in `config.py` will be used. For example, `os.getenv('HOST', '127.0.0.1')` will default to `127.0.0.1` if the `HOST` variable is not configured.

Example `.env` file configuration:

```conf
ASSETS_PATH=C:/Users/Administrator/Pictures,C:/Users/Administrator/Videos
SKIP_PATH=C:/Users/Administrator/AppData
```

If you find that certain formats of images or videos are not being scanned, you can try adding the corresponding file extensions to `IMAGE_EXTENSIONS` and `VIDEO_EXTENSIONS`. If you find that some supported extensions have not been added to the code, please feel free to open an issue or submit a pull request to add them.

If small images are not being scanned, you can try reducing `IMAGE_MIN_WIDTH` and `IMAGE_MIN_HEIGHT` and try again.

If you want to use proxy, you can use `http_proxy` and `https_proxy`. For example: 

```conf
http_proxy=http://127.0.0.1:7070
https_proxy=http://127.0.0.1:7070
```

Note: It is no recommended to set `ASSETS_PATH` as remote directory such as SMB/NFS, which may slow your scanning speed.

## Troubleshooting

If you encounter any issues, please read this documentation carefully first. If you cannot find an answer, search the issues to see if there are similar problems. If not, you can open a new issue and provide detailed information about the problem, including your attempted solutions and thoughts, error messages and screenshots, and the system you are using (Windows/Linux/MacOS) and the configuration (which will be printed while running `main.py`).

I am only responsible for issues related to the functionality, code, and documentation of this project (such as malfunctions, code errors, and incorrect documentation). **Please resolve any runtime environment issues on your own (such as how to configure the Python environment, inability to use GPU acceleration, how to install ffmpeg, etc.).**

I am doing this project purely "for the love of it" (which means, in fact, I am not obligated to answer your questions). To improve the efficiency of problem solving, please provide as much information as possible when opening an issue. If your issue has been resolved, please remember to close it. Issues that receive no response for one week will be closed. If you have resolved the issue on your own before receiving a response, it is recommended to leave the solution so that others may benefit.

## Hardware Requirements

`amd64 (x86_64)` architecture CPU. The minimum requirement is 2GB of memory, but it is recommended to have at least 4GB of memory. If you have a large number of photos, it is recommended to increase the amount of memory.

## Search Speed

Test environment: J3455 CPU, 8GB of memory.

On a J3455 CPU, approximately 31,000 image matches or 25,000 video frame matches can be performed in 1 second.

## Known Issues

1. Some videos cannot be displayed on the web page because the browser does not support that file type (e.g. videos encoded with SVQ3).
2. When you click on an image to enlarge it, some images cannot be displayed because the browser does not support this type of file (e.g. images in tiff format). Small images can be displayed normally because they are converted into thumbnails in a format supported by the browser. Large images use the original file.
3. When searching for videos, if too many videos are displayed and the video size is too large, the computer may freeze, which is normal. So it is suggested that do not select more than 12 results when you searching videos.
