# 异常
alita.exceptions模块定义了Http请求的各类请求码，您也可以定义自己的异常，
如果不是继承自HTTPException，则会被当做500异常处理。

## 异常处理
您可以使用abort函数自动抛出一个异常，可以指定请求代码。
```
from alita.exceptions import abort

@app.route('/')
async def hello(request):
    abort(403)
```

您也可以注册自定义的处理函数，仅当系统发生此请求错误码或该请求类的异常。
from alita.exceptions import NotFound

@app.register_error_handler(NotFound)
async def hello(request):
     return '404 error!'

@app.register_error_handler(404)
async def hello1(request):
     return '404 error!'
```

## 常见异常
- NotFound: 视图函数未发现
- InternalServerError: 发生系统错误