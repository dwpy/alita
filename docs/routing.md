# 路由
使用route()装饰器可以绑定一个函数到一个URL。
```
@app.route('/')
def index():
    return 'Index Page'

@app.route('/hello')
def hello():
    return 'Hello, World'
```
