# 加载配置

## 字典更新
```
app = Alita(__name__)
app.config['DEBUG'] = True
app.config.update(DEBUG=True)
```

## 模块
```
import config
app.config_from_object(config)
```

## Python文件
```
app.config_from_py('config.py')
```

## json文件
```
app.config_from_json('config.json')
```
