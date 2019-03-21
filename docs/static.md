# 静态文件
动态 web 应用也会需要静态文件，通常是 CSS 和 JavaScript 文件。

## 创建静态文件夹
在你的包中或是模块的所在目录中创建一个名为 static 的文件夹。

## 静态文件配置
以下代码示例是实现一个简单的返回文本的蓝图。
```
from alita import Alita

app = Alita('dw', static_folder='static', static_url_path='/static')
```
static_folder指向你创建的文件夹目录，static_url_path代表应用访问静态文件的路由地址，
默认为'/static'。
