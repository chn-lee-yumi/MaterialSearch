"""目前这个脚本是单独运行的"""
import xml.etree.ElementTree as ET

from database import add_pexels_video, is_pexels_video_exist
from models import DatabaseSession, create_tables
from process_assets import process_text, process_web_image

video_sitemap_xml = "video-sitemap10.xml"


# logger = logging.getLogger(__name__)

def handel_xml():
    tree = ET.parse(video_sitemap_xml)
    root = tree.getroot()
    # 找到所有的video元素
    video_elements = root.findall(".//{http://www.google.com/schemas/sitemap-video/1.1}video")
    print("Total videos:", len(video_elements))
    i = 0
    # 遍历每个video元素并提取元数据
    for video_element in video_elements:
        i += 1
        content_loc = video_element.find("{http://www.google.com/schemas/sitemap-video/1.1}content_loc").text
        duration = video_element.find("{http://www.google.com/schemas/sitemap-video/1.1}duration").text
        view_count = video_element.find("{http://www.google.com/schemas/sitemap-video/1.1}view_count").text
        thumbnail_loc = video_element.find("{http://www.google.com/schemas/sitemap-video/1.1}thumbnail_loc").text
        title = video_element.find("{http://www.google.com/schemas/sitemap-video/1.1}title").text
        description = video_element.find("{http://www.google.com/schemas/sitemap-video/1.1}description").text
        # 在这里可以使用提取到的元数据进行处理
        duration = int(duration)
        view_count = int(view_count)
        title = title.strip()
        description = description.strip()
        if title.startswith("Video Of "):
            title = title[len("Video Of "):]
        if title.endswith(" · Free Stock Video"):
            title = title[:-len(" · Free Stock Video")]
        if description.startswith("One of many great free stock videos from Pexels. This video is about "):
            description = description[len("One of many great free stock videos from Pexels. This video is about "):]
        # print("Content Location:", content_loc)
        # print("Duration:", duration)
        # print("View Count:", view_count)
        # print("Thumbnail Location:", thumbnail_loc)
        # print("Title:", title)
        # print("Description:", description)
        # print("----")
        with DatabaseSession() as session:
            if is_pexels_video_exist(session, thumbnail_loc):
                # print(f"视频已存在：{thumbnail_loc}")
                continue
            thumbnail_feature = process_web_image(thumbnail_loc + "?fm=webp&fit=corp&min-w=224&h=224")
            if thumbnail_feature is None:
                print("获取视频缩略图特征失败，跳过该视频")
                continue
            print(f"[{i}/{len(video_elements)}]新增视频：{thumbnail_loc}", end="      \r")
            add_pexels_video(
                session,
                content_loc=content_loc,
                duration=duration,
                view_count=view_count,
                thumbnail_loc=thumbnail_loc,
                title=title,
                description=description,
                title_feature=process_text(title).tobytes(),
                description_feature=process_text(description).tobytes(),
                thumbnail_feature=thumbnail_feature.tobytes(),
            )


if __name__ == '__main__':
    create_tables()
    handel_xml()
