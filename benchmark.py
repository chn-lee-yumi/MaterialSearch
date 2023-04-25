# 模型性能测试，输出模型在不同设备上计算一个图片一百次的运行时间
import time

from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import torch

MODEL_NAME = "openai/clip-vit-base-patch32"
device_list = ["cpu", "cuda"]  # 推理设备，cpu/cuda/mps
image = Image.open("test.jpg")  # 测试图片

print("Loading model...")
model = CLIPModel.from_pretrained(MODEL_NAME)
processor = CLIPProcessor.from_pretrained(MODEL_NAME)
print("Model loaded.")

for device in device_list:
    model = model.to(torch.device(device))
    t0 = time.time()
    for i in range(100):
        inputs = processor(images=image, return_tensors="pt", padding=True).to(torch.device(device))
        feature = model.get_image_features(**inputs).cpu().detach().numpy()
    print(device, time.time() - t0)
