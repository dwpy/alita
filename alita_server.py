import time
import asyncio
from alita import *

app = Alita(static_folder='static')


@app.route("/")
async def index(request):
    await asyncio.sleep(1)
    return HtmlResponse("index page")


if __name__ == '__main__':
    app.run(host='192.168.5.65', port=5011)
