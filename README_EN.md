# MaterialSearch

[**中文**](./README.md) | [**English**](./README_EN.md)

Search local photos and videos through natural language.

## Features

- Text-based image search
- Image-based image search
- Text-based video search (provides matching video clips based on descriptions)
- Image-based video search (searches for video segments based on screenshots)
- Calculation of image-text similarity (provides a score, not very useful)

## Usage Instructions

### Deployment via Source Code

First, install the Python environment and then download the code from this repository.

Note that the first run will automatically download the models. The download speed may be slow, so please be patient. If the network is poor, the model download may fail. In that case, simply rerun the program.

1. Install the dependencies before first use: `pip install -U -r requirements.txt`. For Windows systems, you can double-click on `install.bat` (for NVIDIA GPU acceleration) or `install_cpu.bat` (for pure CPU).
2. If you plan to use GPU acceleration, run the benchmark to determine whether the CPU or GPU is faster: `python benchmark.py`. For Windows systems, you can double-click on `benchmark.bat`. Note that GPU is not necessarily faster than CPU; on my Mac, CPU is faster.
3. If it is not the CPU that is fastest, modify the `DEVICE` and `DEVICE_TEXT` settings in the configuration file to correspond to the appropriate device (refer to the configuration instructions below for how to modify the configuration).
4. Start the program: `python main.py`. For Windows systems, you can double-click on `run.bat`.

If you encounter any issues with the version dependencies in `requirements.txt` (for example, if a library version is too new and causes errors), please provide feedback by opening an issue. I will add version range restrictions.

If you encounter issues with hardware support but are unable to use GPU acceleration, please update the torch version according to the [PyTorch documentation](https://pytorch.org/get-started/locally/).

To use the "Download Video Segments" feature, you need to install `ffmpeg`. If you are using Windows, remember to add the directory where `ffmpeg.exe` is located to the `PATH` environment variable. You can refer to a [Bing search](https://cn.bing.com/search?q=windows+how+to+add+path+environment+variable) for instructions.

### Deployment via Docker

Currently, there is only one Docker image available, which supports both `amd64` and `arm64` architectures. It includes the default models (`openai/clip-vit-base-patch32` and `IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese`) and supports GPU acceleration (only for `amd64` architecture). If you have additional requirements, please open an issue.

Before starting the image, you need to prepare:

1. The path to save the database
2. The scan paths on your local machine and the paths to be mounted inside the container
3. You can configure through modifying the `environment` and `volumes` sections in the `docker-compose.yml` file
4. If you plan to use GPU acceleration, uncomment the corresponding section in the `docker-compose.yml` file

Please refer to the `docker-compose.yml` file for details, as it contains detailed comments.

Finally, execute `docker-compose up -d` to start the container.

Note: It is not recommended to set memory limits for the container, as it may cause strange issues. For example, refer to [this issue](https://github.com/chn-lee-yumi/MaterialSearch/issues/6).

## Configuration Instructions

All configurations are in the `config.py` file, which contains detailed comments.

It is recommended to modify the configuration through environment variables or by creating a `.env` file in the project root directory. If a corresponding variable is not configured, the default value in `config.py` will be used. For example, `os.getenv('HOST', '0.0.0.0')` will default to `0.0.0.0` if the `HOST` variable is not configured.

Example `.env` file configuration:

```
ASSETS_PATH=C:/Users/Administrator/Pictures,C:/Users/Administrator/Videos
DEVICE=cuda
DEVICE_TEXT=cuda
```

The functionality is still being iterated upon, so the configuration may change frequently. If you find that the application fails to start after updating to a new version, please refer to the latest configuration file and manually modify the configuration accordingly.

If you find that certain formats of images or videos are not being scanned, you can try adding the corresponding file extensions to `IMAGE_EXTENSIONS` and `VIDEO_EXTENSIONS`. If you find that some supported extensions have not been added to the code, please feel free to open an issue or submit a pull request to add them.

If small images are not being scanned, you can try reducing `IMAGE_MIN_WIDTH` and `IMAGE_MIN_HEIGHT` and try again.

## Troubleshooting

If you encounter any issues, please read this documentation carefully first. If you cannot find an answer, search the issues to see if there are similar problems. If not, you can open a new issue and provide detailed information about the problem, including your attempted solutions and thoughts, error messages and screenshots, and the system you are using (Windows/Linux/MacOS) and the configuration (which will be printed while running `main.py`).

I am only responsible for issues related to the functionality, code, and documentation of this project (such as malfunctions, code errors, and incorrect documentation). **Please resolve any runtime environment issues on your own (such as how to configure the Python environment, inability to use GPU acceleration, how to install ffmpeg, etc.).**

I am doing this project purely "for the love of it" (which means, in fact, I am not obligated to answer your questions). To improve the efficiency of problem solving, please provide as much information as possible when opening an issue. If your issue has been resolved, please remember to close it. Issues that receive no response for one week will be closed. If you have resolved the issue on your own before receiving a response, it is recommended to leave the solution so that others may benefit.

## Hardware Requirements

It is recommended to use a `amd64` or `arm64` architecture CPU. The minimum requirement is 2GB of memory, but it is recommended to have at least 4GB of memory. If you have a large number of photos, it is recommended to increase the amount of memory.

Test environment: J3455 CPU, 8GB of memory. Allwinner H6, 2GB of memory.

If you are using an AMD GPU, GPU acceleration is only supported on Linux. Please refer to the [PyTorch documentation](https://pytorch.org/get-started/locally/).

## Search Speed

On a J3455 CPU, approximately 17,000 image matches can be performed in 1 second (video matching may be slightly slower).

## Known Issues

1. Some images and videos cannot be displayed on the web page because the browser does not support that file type (such as TIFF files, videos encoded with SVQ3, etc.).

## About Pull Requests

Pull requests are welcome! However, to avoid meaningless work, it is recommended to open an issue for discussion before submitting a pull request.

Before submitting a pull request, please ensure that the code has been formatted.
