# 模型性能基准测试
import time

import torch
from PIL import Image
from transformers import AutoModelForZeroShotImageClassification, AutoProcessor

from config import *

device_list = ["cpu", "cuda", "mps"]  # 推理设备，可选cpu、cuda、mps
image = Image.open("test.png")  # 测试图片。图片大小影响速度，一般相机照片为4000x3000。图片内容不影响速度。
input_text = "This is a test sentence."  # 测试文本
test_times = 100  # 测试次数

print("Loading models...")
clip_model = AutoModelForZeroShotImageClassification.from_pretrained(MODEL_NAME)
clip_processor = AutoProcessor.from_pretrained(MODEL_NAME)
print("Models loaded.")

# 图像处理性能基准测试
print("*" * 50)
print("开始进行图像处理性能基准测试。用时越短越好。")
min_time = float('inf')
recommend_device = ''
for device in device_list:
    try:
        clip_model = clip_model.to(torch.device(device))
    except (AssertionError, RuntimeError):
        print(f"该平台不支持{device}，已跳过。")
        continue
    t0 = time.time()
    for i in range(test_times):
        inputs = clip_processor(images=[image] * SCAN_PROCESS_BATCH_SIZE, return_tensors="pt", padding=True)['pixel_values'].to(torch.device(device))
        feature = clip_model.get_image_features(inputs).detach().cpu().numpy()
    cost_time = time.time() - t0
    print(f"设备：{device} 用时：{cost_time}秒")
    if cost_time < min_time:
        min_time = cost_time
        recommend_device = device
print(f"图像处理建议使用设备：{recommend_device}")

print("*" * 50)
print("测试完毕！")
