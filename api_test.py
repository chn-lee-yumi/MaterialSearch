import time

import pytest
import requests

from utils import get_hash

upload_file = 'test.png'


def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def wait_server_ready():
    for i in range(100):
        try:
            requests.get('http://127.0.0.1:8085/', timeout=1)
        except:
            time.sleep(5)
            continue
        break


def setup_function():
    wait_server_ready()


def test_index():
    # 测试中文网页
    response = requests.get('http://127.0.0.1:8085/', headers={"accept-language": "zh-CN"})
    assert response.status_code == 200
    text = response.text
    index_html = read_file("static/index.html")
    assert text == index_html
    # 测试英文网页
    response = requests.get('http://127.0.0.1:8085/')
    assert response.status_code == 200
    text = response.text
    index_html = read_file("static/index_en.html")
    assert text == index_html


def test_api_scan():
    response = requests.get('http://127.0.0.1:8085/api/scan')
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "start scanning"
    # 马上请求第二次，应该返回正在扫描
    response = requests.get('http://127.0.0.1:8085/api/scan')
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "already scanning"


def test_api_status():
    response = requests.get('http://127.0.0.1:8085/api/status')
    assert response.status_code == 200
    data = response.json()
    assert data["status"] is True
    # 等待扫描完成
    for i in range(100):
        response = requests.get('http://127.0.0.1:8085/api/status')
        data = response.json()
        if data["status"] is not False:
            time.sleep(3)
            continue
        break
    assert data["status"] is False


def test_api_clean_cache():
    response = requests.get('http://127.0.0.1:8085/api/clean_cache')
    assert response.status_code == 204
    response = requests.post('http://127.0.0.1:8085/api/clean_cache')
    assert response.status_code == 204


def test_api_match():
    payload = {
        "positive": "white",
        "negative": "",
        "top_n": "6",
        "search_type": 0,
        "positive_threshold": 10,
        "negative_threshold": 10,
        "image_threshold": 85,
        "img_id": -1,
        "path": "",
    }
    # 文字搜图
    response = requests.post('http://127.0.0.1:8085/api/match', json=payload)
    data = response.json()
    # [{"path":"/home/runner/work/MaterialSearch/MaterialSearch/test.png","score":"11.53","softmax_score":"100.00%","url":"api/get_image/9"}]
    assert len(data) == 1
    assert data[0]["path"] == "/home/runner/work/MaterialSearch/MaterialSearch/test.png"
    assert data[0]["softmax_score"] == 1.0
    # 以图搜图
    with requests.session() as sess:
        # 测试上传图片
        files = {'file': ('test.png', open(upload_file, 'rb'), 'image/png')}
        response = sess.post('http://127.0.0.1:8085/api/upload', files=files)
        assert response.status_code == 200
        # 测试以图搜图
        payload["search_type"] = 1
        response = sess.post('http://127.0.0.1:8085/api/match', json=payload)
        data = response.json()
        assert len(data) == 1
        assert data[0]["path"] == "/home/runner/work/MaterialSearch/MaterialSearch/test.png"
        assert data[0]["softmax_score"] == 1.0
    # 测试下载图片
    image_url = data[0]["url"]
    response = requests.get('http://127.0.0.1:8085/' + image_url)
    assert response.status_code == 200
    hash_origin = ""
    with open(upload_file, "rb") as f:
        hash_origin = get_hash(f)
    hash_download = get_hash(response.content)
    assert hash_origin == hash_download
    # TODO：以数据库的图搜图和视频
    # TODO：文字搜视频
    # TODO：以图搜视频
    # TODO：get_video
    # 路径搜图
    payload["search_type"] = 7
    payload["path"] = "test.png"
    response = requests.post('http://127.0.0.1:8085/api/match', json=payload)
    data = response.json()
    assert len(data) == 1
    assert data[0]["path"] == "/home/runner/work/MaterialSearch/MaterialSearch/test.png"
    assert data[0]["url"] == image_url
    # TODO：路径搜视频


# 运行测试
if __name__ == '__main__':
    pytest.main()
    # TODO: 测试login和logout
