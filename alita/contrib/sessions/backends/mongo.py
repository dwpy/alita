# -*- coding: utf-8 -*-
from mongoengine import *
from datetime import datetime
from dateutil.relativedelta import relativedelta
from alita.contrib.sessions.backends.base import *


class SessionManager(SessionInterface):
    def init(self):
        class Session(Document):
            meta = {
                'db_alias': self.client_config['db'],
                "collection": self.session_table_name,
                'index_background': True,
                'indexes': ['session_key', "expire_date"]}

            session_key = StringField(max_length=40)
            session_data = StringField()
            expire_date = DateTimeField()
            created = DateTimeField(default=datetime.now)
        self.session_model = Session
        register_connection(self.client_config['db'], **self.client_config)

    async def delete(self, session_key):
        self.session_model.objects(session_key=session_key).delete()

    async def exists(self, session_key):
        return self.session_model.objects(session_key=session_key).first()

    async def get(self, request, session_key):
        return self.session_model.objects(
            session_key=session_key,
            expire_date__gt=datetime.now()).first()

    async def save(self, request):
        data = self.get_session_data(request.session)
        session = await self.exists(data['session_key'])
        if not session:
            session = self.session_model(**data)
            session.save()
        else:
            if self.must_save:
                session.session_data = data['session_data']
                session.expire_date = data['expire_date']
                session.save()
            else:
                raise UpdateError

    def clear_expired(self, months=1):
        _date = datetime.now() + relativedelta(months=-months)
        self.session_model.objects(expire_date__lt=_date).delete()
