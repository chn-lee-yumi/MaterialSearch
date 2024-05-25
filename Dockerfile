# 本Dockerfile构建对应的参数为：
# MODEL_NAME = "OFA-Sys/chinese-clip-vit-base-patch16"
FROM python:3.11
WORKDIR /MaterialSearch/
ENV HF_HOME=/MaterialSearch/transformers/
RUN apt update && apt install -y ffmpeg && apt clean
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c 'from transformers import AutoModelForZeroShotImageClassification, AutoProcessor; AutoModelForZeroShotImageClassification.from_pretrained("OFA-Sys/chinese-clip-vit-base-patch16"); AutoProcessor.from_pretrained("OFA-Sys/chinese-clip-vit-base-patch16");'
COPY *.py ./
COPY static/ ./static/
ENV TRANSFORMERS_OFFLINE=1
ENTRYPOINT ["python", "main.py"]
