# WebSocket
WebSocket是HTML5开始提供的一种在单个TCP连接上进行全双工通讯的协议。

## 视图
```
@app.websocket('/ws')
async def websocket_view(ws, request):
    message = await ws.recv()
    await ws.send(message)
```

## 蓝图视图
```
from alita import Blueprint

bp = Blueprint('abc')

@bp.websocket('/ws')
async def websocket_view(ws, request):
    message = await ws.recv()
    await ws.send(message)
```
