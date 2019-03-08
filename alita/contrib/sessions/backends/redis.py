# -*- coding: utf-8 -*-
from redis import Redis
from alita.utils import cached_property
from alita.contrib.sessions.backends.base import *


class SessionManager(SessionInterface):

    @cached_property
    def client(self):
        return Redis(**self.client_config)

    async def delete(self, session_key):
        self.client.delete(session_key)

    async def exists(self, session_key):
        return self.client.get(session_key)

    def get_session_data(self, session):
        return dict(
            name=self.get_session_key(session),
            value=self.encode(session),
            time=self.get_expiry_age(session)
        )

    async def get(self, request, session_key):
        return self.client.get(session_key)

    async def save(self, request):
        self.client.setex(**self.get_session_data(request.session))


