# MaterialSearch

Search local photos and videos through natural language.
扫描本地的图片以及视频，并通过AI识别，最后可以自然语言对扫描结果进行查找

已知问题：

1. 部分图片和视频无法在网页上显示，原因是浏览器不支持这一类型的文件（例如tiff文件，svq3编码的视频等）。

2. 暂时无法通过多进程优化查询速度。
3. 网页查找时只能用cpu推理，cuda只能用在扫描图片与视频文件上；

## 安装依赖
`pip install -r requirements.txt`

## 首次启动-windows
1. Windows系统，双击“性能测试.bat”；![image-20230511225958063](F:\个人\MaterialSearch\image-20230511225958063.png)

2. 在生成的benchmark.txt中比较下是cuda执行的快还是cpu执行的快；

3. 如果是cuda执行的快，那么就在config.py中把第17行的`DEVICE = "cpu"`  改为 `DEVICE = "cuda"`  ，修改后保存文件；

4. windows系统的，双击“启动.bat”，没显示文件扩展名的话那看到的就是“启动”。![image-20230511230036057](F:\个人\MaterialSearch\image-20230511230036057.png)

   

## 首次启动-Linux/Ununtu

1. 进入到项目目录；
2. 输入命令 `python benchmark.py`,运行性能测试；
3. 输入命令 `cat enchmark.txt`,查看文件内容比较出是cuda快还是cpu执行的快；
4. 如果是cuda执行的快，那么就在config.py中把第17行的`DEVICE = "cpu"`  改为 `DEVICE = "cuda"`  ；
5. 输入命令`python main.py`


## 日常使用-Windows
1. windows系统的，双击“启动.bat”，没显示文件扩展名的话那看到的就是“启动”。
