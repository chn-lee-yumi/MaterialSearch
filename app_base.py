from flask import Flask

app = Flask('main')  # 兼容曾经的数据库路径
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///assets.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True
app.secret_key = "https://github.com/chn-lee-yumi/MaterialSearch"
