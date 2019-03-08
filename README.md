## Alita

Alita is a lightweight python async web application framework,\
It need Python3.5+ version at least。


## Installing
```
pip install -r requirements.txt
```

## Quick Start

```
from alita import Alita

app = Alita()

@app.route('/')
async def hello(request):
    return 'Hello, World!'
```

## Links

- Code: https://github.com/dwpy/alita
- Docs: https://dwpy.github.io/alita
