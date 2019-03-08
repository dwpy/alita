# -*- coding: utf-8 -*-
import base64
from uuid import uuid4
from collections import MutableMapping
from itsdangerous import Signer
from datetime import datetime, timedelta
from alita.datastructures import CallbackDict
from itsdangerous import want_bytes, BadSignature
from alita.base import JSONSerializer


class UpdateError(Exception):
    pass


class SessionMixin(MutableMapping):
    """Expands a basic dictionary with session attributes."""

    @property
    def permanent(self):
        """This reflects the ``'_permanent'`` key in the dict."""
        return self.get('_permanent', False)

    @permanent.setter
    def permanent(self, value):
        self['_permanent'] = bool(value)

    #: Some implementations can detect whether a session is newly
    #: created, but that is not guaranteed. Use with caution. The mixin
    # default is hard-coded ``False``.
    new = False

    #: Some implementations can detect changes to the session and set
    #: this when that happens. The mixin default is hard coded to
    #: ``True``.
    modified = True

    #: Some implementations can detect when session data is read or
    #: written and set this when that happens. The mixin default is hard
    #: coded to ``True``.
    accessed = True


class BaseSessionInterface(object):
    pickle_based = False

    def __init__(self, app, key_prefix=None, use_signer=False, permanent=False):
        self.app = app
        self.key_prefix = key_prefix or self.app.key_prefix or ''
        self.use_signer = use_signer or self.app.session_use_signer
        self.permanent = permanent

    def init(self):
        pass

    async def get_session(self, request):
        """This method has to be implemented and must either return ``None``
        in case the loading failed because of a configuration error or an
        instance of a session object which implements a dictionary like
        interface + the methods and attributes on :class:`SessionMixin`.
        """
        raise NotImplementedError()

    async def save_session(self, request):
        """This is called for actual sessions returned by :meth:`open_session`
        at the end of the request.  This is still called during a request
        context so if you absolutely need access to the request you can do
        that.
        """
        raise NotImplementedError()

    def get_session_id(self, request):
        raise NotImplementedError()

    def get_expiry_age(self, session, **kwargs):
        try:
            modification = kwargs['modification']
        except KeyError:
            modification = datetime.now()
        try:
            expiry = kwargs['expiry']
        except KeyError:
            expiry = session.session_expiry

        if not expiry:
            return self.app.session_cookie_expire
        if not isinstance(expiry, datetime):
            return expiry
        delta = expiry - modification
        return delta.days * 86400 + delta.seconds

    def get_expiry_date(self, session, **kwargs):
        try:
            modification = kwargs['modification']
        except KeyError:
            modification = datetime.now()
        try:
            expiry = kwargs['expiry']
        except KeyError:
            expiry = session.session_expiry

        if isinstance(expiry, datetime):
            return expiry
        expiry = expiry or self.app.session_cookie_expire
        return modification + timedelta(seconds=expiry)


class Session(CallbackDict, SessionMixin):
    _expiry_key_name = "_session_expiry"
    _ignore_keys = [_expiry_key_name]

    def __init__(self, initial=None, session_id=None, permanent=None):
        def on_update(self):
            self.modified = True
        super(Session, self).__init__(initial, on_update)
        self.session_id = session_id
        if permanent:
            self.permanent = permanent
        self.modified = False

    @property
    def session_expiry(self):
        return self.get(self._expiry_key_name)

    def is_empty(self):
        data = dict(self)
        for key in self._ignore_keys:
            data.pop(key, None)
        return not bool(data)

    def set_expiry(self, expiry_time, force=True):
        if expiry_time is None:
            try:
                del self[self._expiry_key_name]
            except KeyError:
                pass
            return
        if force or not self.session_expiry:
            self[self._expiry_key_name] = expiry_time


class SessionManagerMixin:
    def clear_expired(self):
        pass

    def create_table(self):
        pass

    async def exists(self, session_key):
        raise NotImplementedError()

    async def delete(self, session_key):
        raise NotImplementedError()

    async def get(self, request, session_key):
        raise NotImplementedError()

    async def save(self, request):
        raise NotImplementedError()


class SessionInterface(BaseSessionInterface, SessionManagerMixin):
    session_class = Session
    charset = 'utf-8'

    def __init__(self, app, key_prefix=None, use_signer=False, permanent=False):
        super(SessionInterface, self).__init__(app, key_prefix, use_signer, permanent)
        self.client_config = self.app.session_engine_config
        self.must_save = self.app.config.get('SESSION_MUST_SAVE', True)
        self.serializer = JSONSerializer()
        self.session_model = None
        self.session_table_name = self.app.session_table_name
        self.init()

    def _generate_session_id(self):
        return uuid4().hex

    def _get_signer(self):
        if not self.app.secret_key:
            return None
        return Signer(
            self.app.secret_key,
            salt='alita-session',
            key_derivation='hmac'
        )

    def get_session_key(self, session):
        if isinstance(session, str):
            return self.key_prefix + session
        elif isinstance(session, Session):
            return self.key_prefix + session.session_id
        else:
            raise TypeError("get session key params must bu "
                            "session_id or session object")

    def get_session_id(self, request):
        if self.use_signer:
            return self._get_signer().sign(want_bytes(request.session.session_id))
        else:
            return request.session.session_id

    def encode(self, session_dict):
        serialized = self.serializer.dumps(session_dict)
        return base64.b64encode(serialized.encode(self.charset)).decode(self.charset)

    def decode(self, session_data):
        if hasattr(session_data, 'session_data'):
            session_data = session_data.session_data
        if isinstance(session_data, str):
            session_data = session_data.encode(self.charset)
        serialized = base64.b64decode(session_data)
        return self.serializer.loads(serialized)

    def get_session_data(self, session):
        return dict(
            session_key=self.get_session_key(session),
            session_data=self.encode(session),
            expire_date=self.get_expiry_date(session)
        )

    async def get_session(self, request):
        session_id = request.cookies.get(self.app.session_cookie_name)
        if not session_id:
            session_id = self._generate_session_id()
            return self.session_class(
                session_id=session_id,
                permanent=self.permanent
            )
        if self.use_signer:
            try:
                signer = self._get_signer()
                if not signer:
                    raise BadSignature
                session_id_as_bytes = signer.unsign(session_id)
                session_id = session_id_as_bytes.decode()
            except BadSignature:
                session_id = self._generate_session_id()
                return self.session_class(
                    session_id=session_id,
                    permanent=self.permanent
                )
        session_key = self.get_session_key(session_id)
        val = await self.get(request, session_key)
        if val is not None:
            val = self.decode(val)
        return self.session_class(
            initial=val,
            session_id=session_id,
            permanent=self.permanent
        )

    async def save_session(self, request):
        raise self.save(request)

    async def cycle_session(self, session):
        session_key = self.get_session_key(session.session_id)
        if session_key and self.exists(session_key):
            self.delete(session_key)
        session.session_id = self._generate_session_id()


class NullSession(SessionInterface):
    async def get(self, request, session_key):
        return None

    async def save(self, request):
        pass


__all__ = [
    "NullSession",
    "SessionInterface",
    "UpdateError"
]
