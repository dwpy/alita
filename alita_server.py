import time
import asyncio
from alita import *

app = Alita()


@app.route("/")
async def index(request):
    await asyncio.sleep(1)
    return HtmlResponse("index page")


@app.route('/stats/{name:str}')
async def hello_world1(request, name):
    return 'Hello World!'


if __name__ == '__main__':
    app.run(host='192.168.5.65', port=5011)
