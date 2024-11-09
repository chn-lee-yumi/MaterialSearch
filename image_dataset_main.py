from torch.utils.data import Dataset
from PIL import Image
from pillow_heif import register_heif_opener
register_heif_opener() # 必须在这里再运行一次
import logging
logger = logging.getLogger(__name__)
# from config import AUTOPROCESSOR_BATCH_SIZE # 放这里边老是输出那一堆配置


class ImageDataset(Dataset):
    def __init__(self, processor, AUTOPROCESSOR_BATCH_SIZE , image_paths):
        """
        :param processor: 用于预处理的处理器（如 clip_processor）
        :param image_paths: 包含图像路径的列表
        """
        self.processor = processor
        self.autoprocessor_batch_size = AUTOPROCESSOR_BATCH_SIZE
        self.image_paths = image_paths

    def __len__(self):
        # 计算数据集的长度，基于路径列表和批大小
        return len(self.image_paths) // self.autoprocessor_batch_size

    def __getitem__(self, idx):
        """
        获取索引 idx 的批次数据，将 autoprocessor_batch_size 张图片传入 processor。
        """
        # 获取该批次的图像路径
        start_idx = idx * self.autoprocessor_batch_size
        end_idx = start_idx + self.autoprocessor_batch_size
        batch_paths = self.image_paths[start_idx:end_idx]

        images = []
        for path in batch_paths:
            try:
                img = Image.open(path)
                images.append(img)
            except Exception as e:
                logger.warning(f"打开图片报错： {repr(e)}")

        # 使用 processor 对图像进行预处理
        inputs = self.processor(
            images=images, # 8图片 大概占用1GB内存
            return_tensors="pt",
            padding=True
        )['pixel_values']

        return inputs, batch_paths
