# -*- coding: utf-8 -*-
signals_available = False
try:
    from blinker import Namespace
    signals_available = True
except ImportError:
    class Namespace(object):
        def signal(self, name, doc=None):
            return _FakeSignal(name, doc)

    class _FakeSignal(object):
        def __init__(self, name, doc=None):
            self.name = name
            self.__doc__ = doc

        def _fail(self, *args, **kwargs):
            raise RuntimeError('signalling support is unavailable '
                               'because the blinker library is '
                               'not installed.')
        send = lambda *a, **kw: None
        connect = disconnect = has_receivers_for = receivers_for = \
            temporarily_connected_to = connected_to = _fail
        del _fail

_signals = Namespace()

request_started = _signals.signal('request-started')
request_finished = _signals.signal('request-finished')
got_request_exception = _signals.signal('got-request-exception')
message_flashed = _signals.signal('message-flashed')
template_rendered = _signals.signal('template-rendered')
before_render_template = _signals.signal('before-render-template')
