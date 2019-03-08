# 快速开始

## 运行环境
> Python3.5+


## 安装
> python3 -m pip install alita

## 示例项目
```
from alita import Alita
app = Alita()

@app.route('/')
async def hello(request):
    return 'Hello World!'

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
```

启动服务器: `python3 main.py` \
在你的浏览器打开地址 `http://0.0.0.0:8000`，你会看到 *Hello World!*。

