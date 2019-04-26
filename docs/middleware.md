# 中间件

## 请求中间件
通过在视图函数处理请求前调用用户自定义处理函数，以修改请求对象。
```
@app.request_middleware
def process_request(request):
    return request
```

## 响应中间件
通过在视图函数处理请求后调用用户自定义处理函数，以修改响应对象。
```
@app.response_middleware
def process_response(request, response):
    return response
```

## 全局视图处理函数
```
@app.view_handler
def auth(**options):
    print(options.get('template'))
    
    def entangle(func):
        @functools.wraps(func)
        async def wrapper(*sub, **kwargs):
            return await func(*sub, **kwargs)
        return wrapper
    return entangle

@app.route('/', template='index.html')
async def index(request):
    return await render_template(request, 'index.html')
```

说明:

- 使用app.view_handler装饰器可将自定义函数装饰到所有视图上，如果使用蓝图的view_handler，
则只装饰到蓝图的视图上。
- 视图处理函数必须使用**options接收app.route路由装饰器的自定义参数。如上示例中，options可以取到route路由器中的
template参数，但是切记要做兼容处理，因为自定义视图处理函数是用来专门处理路由上定义了您需要的参数的一种方式。
