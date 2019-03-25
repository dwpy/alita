# 配置项

## DEBUG

- 默认值：`False`

是否开启DEBUG模式，开启后可以看到详细错误，修改代码后不用重启就可以autoreload

## SECRET_KEY

- 默认值：`None`

密钥。

## MAX_CONTENT_LENGTH

- 默认值：`None`

如果设置为字节数， `Alita`会拒绝内容长度大于此值的请求进入，并返回一个 413 状态码。


## SEND_FILE_MAX_AGE

- 默认值：`12 * 60 * 60`

默认缓存控制的最大期限，以秒计。


## SESSION_COOKIE_NAME

- 默认值：`sessionid`

会话 cookie 的名称。

## SESSION_COOKIE_EXPIRE

- 默认值：`None`

会话 cookie 的有效时间。

## SESSION_COOKIE_DOMAIN

- 默认值：`None`

会话 cookie 的域。

## SESSION_COOKIE_PATH

- 默认值：`None`

会话 cookie 的路径。

## SESSION_COOKIE_HTTPONLY

- 默认值：`True`

控制 cookie 是否应被设置 httponly 的标志。

## SESSION_COOKIE_SECURE

- 默认值：`False`

控制 cookie 是否应被设置安全标志。

## SESSION_COOKIE_SAMESITE

- 默认值：`None`

控制 cookie 跨站请求伪造。

## SESSION_KEY_PREFIX

- 默认值：``

session_key前缀。

## SESSION_USE_SIGNER

- 默认值：`False`

sessionid是否需要签名，与SECRET_KEY配合使用。

## SESSION_SAVE_EVERY_REQUEST

- 默认值：`False`

控制是否每次请求都需要保存session。


## SESSION_EXPIRE_AT_BROWSER_CLOSE

- 默认值：`False`

控制是否在页面关闭后session即失效。

## SESSION_TABLE_NAME

- 默认值：`session`

session存储表名称。

## SESSION_ENGINE

- 默认值：`None`

session管理组件。

## SESSION_ENGINE_CONFIG

- 默认值：`None`

session管理组件数据库配置。


