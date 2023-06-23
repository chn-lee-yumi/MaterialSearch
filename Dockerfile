# 本Dockerfile构建对应的参数为：
# LANGUAGE = "Chinese"
# MODEL_NAME = "openai/clip-vit-base-patch32"
# TEXT_MODEL_NAME = "IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese"
FROM python:bullseye
WORKDIR /MaterialSearch/
ENV TRANSFORMERS_CACHE=/MaterialSearch/transformers/
RUN apt update && apt install -y ffmpeg && apt clean
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
#RUN python -c 'from transformers import CLIPProcessor, CLIPModel, BertTokenizer, BertForSequenceClassification; CLIPModel.from_pretrained("openai/clip-vit-base-patch32"); CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32"); BertTokenizer.from_pretrained("IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese"); BertForSequenceClassification.from_pretrained("IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese")'
# 由于 GitHub Actions 同时构建多个镜像，为了避免重复下载多次模型，这里直接从已经下载好的目录复制过去。如果是本地构建，则注释掉下面一行，并取消注释上面一行
COPY /home/runner/transformers/ ./transformers/
COPY *.py ./
COPY static/ ./static/
ENTRYPOINT ["python", "main.py"]
