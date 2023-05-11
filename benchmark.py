# 模型性能测试，输出模型在不同设备上计算一个图片一百次的运行时间
import time

from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import torch
import logging

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(pathname)s %(message)s "#配置输出日志格式
DATE_FORMAT = '%Y-%m-%d  %H:%M:%S %a ' #配置输出时间的格式，注意月份和天数不要搞乱了
logging.basicConfig(level=logging.DEBUG,
                    format=LOG_FORMAT,
                    datefmt = DATE_FORMAT ,
                    filename=r"benchmark.txt" #有了filename参数就不会直接输出显示到控制台，而是直接写入文件
                    )

MODEL_NAME = "openai/clip-vit-base-patch32"
device_list = ["cpu", "cuda"]  # 推理设备，cpu/cuda/mps


def s2format(secondtimes):
    '''
    把秒数转为时分秒的格式
    :secondtimes,int,传入的秒数，seconds

    return: str,12:21:12,format(hh:mi:ss),小时:分钟:秒
    '''
    m, s = divmod(secondtimes, 60)
    h, m = divmod(m, 60)
    return str("%02d:%02d:%02d"%(h,m,s))

def main(imagelist):
    '''
    CPU跟CUDA性能跑分，每个图片跑100次，哪个用时更短就哪个更快，把process_assets.py第18行的DEVICE ="cpu"进行修改，一般cuda是远快于cpu的，但是显卡性能低的时候两者可能相差不大
    :imagelist,list,图片列表
    '''
    logging.info("Loading model...")
    model = CLIPModel.from_pretrained(MODEL_NAME)
    processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    logging.info("Model loaded.")
    result=[]
    for img in imagelist:
        image = Image.open(img)  # 测试图片
        for device in device_list:
            logging.info(f'开始{device}图像处理的性能测试')
            logging.info(f'本次处理{img}')
            model = model.to(torch.device(device))
            t0 = time.time()
            for i in range(100):
                if (i+1)%20==0:logging.info(f'{img}的第 {i+1} 次')
                inputs = processor(images=image, return_tensors="pt", padding=True).to(torch.device(device))
                feature = model.get_image_features(**inputs).cpu().detach().numpy()

            end_time= time.time()
            result.append(len(imagelist),'组图片，使用',(device,' 总共用时:', s2format(end_time - t0),' ，平均', s2format((end_time- t0) / len(imagelist)), ' /100个'))
    logging.info('=='*16)
    logging.info('汇总结果如下：\n')
    logging.info(f'{result}')
    logging.info('=='*16)

if __name__=='__main__':
    imagelist = ('test (3).png',
'test (2).png',
'test (1).png',
'test (4).jpeg',
'test (3).jpeg',
'test (2).jpeg',
'test (1).jpeg',
'test (8).png',
'test (7).png',
'test (5).png',)
    main(imagelist)