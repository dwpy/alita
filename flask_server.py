import time
from flask import Flask

app = Flask(__name__)


@app.route('/')
def hello_world():
    time.sleep(1)
    return 'Hello World!'


@app.route('/stats/requests')
def hello_world1():
    return 'Hello World!'


@app.route('/does_not_exist')
def hello_world2():
    return 'Hello World!'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5012)
