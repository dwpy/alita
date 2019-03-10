# 响应

## 文本
```
from alita.response import TextResponse
@app.route('/')
async def hello(request):
    return TextResponse('Hello World!')
```

## Html
```
from alita.response import HtmlResponse
@app.route('/')
async def hello(request):
    return HtmlResponse('Hello World!')
```

## 字典
```
from alita.response import JsonResponse
@app.route('/')
async def hello(request):
    return JsonResponse('Hello World!')
```

## 文件
```
from alita.response import FileResponse
@app.route('/')
async def hello(request):
    return FileResponse('static/test.txt')
```

## 重定向
```
from alita.response import RedirectResponse
@app.route('/')
async def hello(request):
    return RedirectResponse('/user')
```
注：如果未制定具体响应类，则根据返回的类型自动匹配，如返回字符串则使用TestResponse，如返回字典或列表则返回JsonResponse对象。
