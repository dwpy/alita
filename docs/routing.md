# 路由

## 定义路由
使用route()装饰器可以绑定一个函数到一个URL。
```
@app.route('/hello')
def hello(request):
    return 'Hello World'
```
也可以使用add_url_rule方法添加视图函数，例如：
```
def hello(request):
    return 'Hello World'
app.add_url_rule(hello, '/hello')
```

## 路由参数
路由地址中可以加入自定义变量，传递给视图函数，支持str，int，float，path四种类型变量，
如果视图参数中没有定义该变量名，则在接口调用时会报错，示例如下：
```
@app.route('/user/<name:str>')
def hello(request, name):
    return 'Hello World, %s' % name
```
注：如果写成<name>，则默认为str。

## route()函数参数
- methods: 视图函数的请求方式，默认是'GET' 。
- endpoint: 视图函数与路由规则的映射端点，用户可自定义该值，默认为视图函数名。