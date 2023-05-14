# 模型性能基准测试
import time

import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel, BertTokenizer, BertForSequenceClassification

from config import *

device_list = ["cpu", "cuda", "mps"]  # 推理设备，可选cpu、cuda、mps
image = Image.open("test.png")  # 测试图片。图片大小影响速度，一般相机照片为4000x3000。图片内容不影响速度。
input_text = "This is a test sentence."  # 测试文本
test_times = 100  # 测试次数

print(f"你使用的语言为{LANGUAGE}。")
print("Loading models...")
clip_model = CLIPModel.from_pretrained(MODEL_NAME)
clip_processor = CLIPProcessor.from_pretrained(MODEL_NAME)
if LANGUAGE == "Chinese":
    text_tokenizer = BertTokenizer.from_pretrained(TEXT_MODEL_NAME)
    text_encoder = BertForSequenceClassification.from_pretrained(TEXT_MODEL_NAME).eval()
print("Models loaded.")

# 图像处理性能基准测试
print("*" * 50)
print("开始进行图像处理性能基准测试。用时越短越好。")
min_time = float('inf')
recommend_device = ''
for device in device_list:
    try:
        clip_model = clip_model.to(torch.device(device))
    except AssertionError:  # AssertionError: Torch not compiled with CUDA enabled
        print(f"该平台不支持{device}，已跳过。")
        continue
    t0 = time.time()
    for i in range(test_times):
        inputs = clip_processor(images=image, return_tensors="pt", padding=True)['pixel_values'].to(torch.device(device))
        feature = clip_model.get_image_features(inputs).detach().cpu().numpy()
    cost_time = time.time() - t0
    print(f"设备：{device} 用时：{cost_time}秒")
    if cost_time < min_time:
        min_time = cost_time
        recommend_device = device
print(f"图像处理建议使用设备：{recommend_device}")

# 文字处理性能基准测试
print("*" * 50)
print("开始进行文字处理性能基准测试。用时越短越好。")
min_time = float('inf')
recommend_device = ''
for device in device_list:
    try:
        if LANGUAGE == "Chinese":
            text_encoder = text_encoder.to(torch.device(device))
        else:
            clip_model = clip_model.to(torch.device(device))
    except AssertionError:
        print(f"该平台不支持{device}，已跳过。")
        continue
    t0 = time.time()
    for i in range(test_times):
        if LANGUAGE == "Chinese":
            text = text_tokenizer(input_text, return_tensors='pt', padding=True)['input_ids'].to(torch.device(device))
            text_features = text_encoder(text).logits.detach().cpu().numpy()
        else:
            text = clip_processor(text=input_text, return_tensors="pt", padding=True)['input_ids'].to(torch.device(device))
            text_features = clip_model.get_text_features(text).detach().cpu().numpy()
    cost_time = time.time() - t0
    print(f"设备：{device} 用时：{cost_time}秒")
    if cost_time < min_time:
        min_time = cost_time
        recommend_device = device
print(f"文字处理建议使用设备：{recommend_device}")

print("*" * 50)
print("测试完毕！")
