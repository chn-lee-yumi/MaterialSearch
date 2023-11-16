# 本Dockerfile构建对应的参数为：
# LANGUAGE = "Chinese"
# MODEL_NAME = "openai/clip-vit-base-patch32"
# TEXT_MODEL_NAME = "IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese"
FROM python:3.11
WORKDIR /MaterialSearch/
ENV TRANSFORMERS_CACHE=/MaterialSearch/transformers/
RUN apt update && apt install -y ffmpeg && apt clean
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c 'from transformers import CLIPProcessor, CLIPModel, BertTokenizer, BertForSequenceClassification; CLIPModel.from_pretrained("openai/clip-vit-base-patch32"); CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32"); BertTokenizer.from_pretrained("IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese"); BertForSequenceClassification.from_pretrained("IDEA-CCNL/Taiyi-CLIP-Roberta-102M-Chinese")'
COPY *.py ./
COPY static/ ./static/
ENTRYPOINT ["python", "main.py"]
