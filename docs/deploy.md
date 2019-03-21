# 部署

## 本地部署
如果您只想在本地部署web应用，目前alita只支持单继承，您可以像如下示例代码这样创建一个app文件。
```
from alita import Alita

app = Alita('dw')


@app.route('/hello')
async def hello(request):
    return 'Hello, World!'


if __name__ == '__main__':
    app.run()
```

## 启动参数
- host：服务器地址
- port：服务器断开
- debug：是否debug模式

## 使用Gunicorn部署
Gunicorn 是一个 UNIX 下的 WSGI HTTP 服务器。您需要指定worker-class参数，以运行alita应用。
```
gunicorn app:app -b 0.0.0.0:8000 -k alita.GunicornWorker
```
关于gunicorn的使用请查阅官方文档。
