# 蓝图
蓝图(blueprints)的概念来在一个应用中或跨应用制作应用组件和支持通用的模式。蓝图很好地简化了大型应用工作的方式，并提供给 Alita 扩展在应用上注册操作的核心方法。

## 创建蓝图
以下代码示例是实现一个简单的返回文本的蓝图。
```
from alita import Blueprint

bp = Blueprint('abc')

@bp.route('/hello')
async def hello(request):
    return 'Hello, World!'

```

## 注册蓝图
以下代码示例是将上述新建的bp蓝图注册到app中。
```
from alita import Alita

app = Alita('dw')
app.register_blueprint(bp, url_prefix='/api')
```
请求/api/hello即可返回'Hello, World!'响应内容。
