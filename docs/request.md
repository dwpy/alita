# 请求

## 请求数据
客户端在调用服务器接口时，会建立request请求对象，并传递给视图函数，request对象包含以下数据：

- json(dict)：请求体json数据。
- args(dict)：URL请求参数字典。
- body(bytes)：原始请求体数据。
- headers(dict)：请求头数据。
- cookies(dict)：cookie数据。
- method(str)：请求方式。
- host(str)：请求host地址。
- port(int)：请求端口。
- path(str)：请求路径。
- app(object)：app对象。
- query_string(str)：请求参数字符串。