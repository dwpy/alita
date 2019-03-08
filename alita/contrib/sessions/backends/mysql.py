# -*- coding: utf-8 -*-
from sqlalchemy import Column, String, Text, DateTime, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from alita.utils import cached_property
from dateutil.relativedelta import relativedelta
from alita.contrib.sessions.backends.base import *
from sqlalchemy.engine import url
from sqlalchemy.exc import ProgrammingError

Base = declarative_base()


class SessionManager(SessionInterface):
    def init(self):
        class Session(Base):
            session_key = Column('session_key', String(40), primary_key=True)
            session_data = Column('session_data', Text())
            expire_date = Column('expire_date', DateTime(), index=True)
            created = Column('created', DateTime(), default=datetime.now)

            __tablename__ = self.session_table_name
        self.session_model = Session
        if 'drivername' not in self.client_config:
            self.client_config['drivername'] = 'mysql+pymysql'

    def create_table(self):
        engine = create_engine(url.URL(**self.client_config))
        Base.metadata.create_all(engine)

    @cached_property
    def client(self):
        engine = create_engine(url.URL(**self.client_config))
        return sessionmaker(bind=engine)()

    async def delete(self, session_key):
        try:
            self.client.query(self.session_model).filter(
                self.session_model.session_key == session_key).delete()
            self.client.commit()
        except self.session_model.DoesNotExist:
            pass

    async def exists(self, session_key):
        return self.client.query(self.session_model).filter(
            self.session_model.session_key == session_key
        ).first()

    async def get(self, request, session_key):
        try:
            return self.client.query(self.session_model).filter(
                self.session_model.session_key == session_key,
                self.session_model.expire_date > datetime.now()
            ).first()
        except ProgrammingError:
            self.create_table()
            val = await self.get(request, session_key)
            return val

    async def save(self, request):
        data = self.get_session_data(request.session)
        session = await self.exists(data['session_key'])
        if not session:
            session = self.session_model(**data)
            self.client.add(session)
            self.client.commit()
        else:
            if self.must_save:
                session.session_data = data['session_data']
                session.expire_date = data['expire_date']
                self.client.commit()
            else:
                raise UpdateError

    def clear_expired(self, months=1):
        _date = datetime.now() + relativedelta(months=-months)
        self.client.query(self.session_model).filter(
            self.session_model.expire_date < _date).delete()
        self.client.commit()
