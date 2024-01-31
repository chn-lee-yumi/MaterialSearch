# image: id, url, features
# video: id, url, frame_time, features
import os

os.environ["FRAME_INTERVAL"] = "6"

import json
import xml.etree.ElementTree as ET
import random
from process_assets import process_video, process_web_image

database_path = "../MaterialSearchWebDemo/static/database.json"

PHOTO_LIMIT = 300
VIDEO_LIMIT = 50

# with open(database_path, "r") as f:
#     database = json.load(f)
database = {
    "photos": [],
    "videos": {}
}


def is_video_exist(url):
    return url in database["videos"]


def is_photo_exist(url):
    for item in database["photos"]:
        if item["url"] == url:
            return True
    return False


def handle_videos():
    tree = ET.parse("sitemaps/pexels_video/video-sitemap10.xml")
    root = tree.getroot()
    elements = root.findall(".//{http://www.google.com/schemas/sitemap-video/1.1}video")
    print("Total videos:", len(elements))
    i = 0
    random.shuffle(elements)
    for element in elements[:VIDEO_LIMIT]:
        i += 1
        content_loc = element.find("{http://www.google.com/schemas/sitemap-video/1.1}content_loc").text
        if is_video_exist(content_loc):
            print(f"[{i}/{VIDEO_LIMIT}]视频已存在：{content_loc}")
            continue
        print(f"[{i}/{VIDEO_LIMIT}]新增视频：{content_loc}")
        database["videos"][content_loc] = []
        for frame_time, features in process_video(content_loc):
            database["videos"][content_loc].append({"frame_time": frame_time, "features": features.tolist()})


def handle_photos():
    tree = ET.parse("sitemaps/pexels_photo/photo-sitemap44.xml")
    root = tree.getroot()
    elements = root.findall(".//{http://www.google.com/schemas/sitemap-image/1.1}image")
    print("Total photos:", len(elements))
    i = 0
    random.shuffle(elements)
    for element in elements[:PHOTO_LIMIT]:
        i += 1
        content_loc = element.find("{http://www.google.com/schemas/sitemap-image/1.1}loc").text
        if is_photo_exist(content_loc):
            print(f"[{i}/{PHOTO_LIMIT}]图片已存在：{content_loc}")
            continue
        print(f"[{i}/{PHOTO_LIMIT}]新增图片：{content_loc}")
        database["photos"].append({"url": content_loc, "features": process_web_image(content_loc).tolist()[0]})


if __name__ == '__main__':
    handle_photos()
    handle_videos()
    database["total_images"] = len(database["photos"])
    database["total_videos"] = len(database["videos"])
    total_video_frames = 0
    for _, v in database["videos"].items():
        total_video_frames += len(v)
    database["total_video_frames"] = total_video_frames
    print("total_images:", len(database["photos"]), "total_video_frames:", total_video_frames, "total_videos:", len(database["videos"]))
    with open(database_path, "w") as f:
        json.dump(database, f)
