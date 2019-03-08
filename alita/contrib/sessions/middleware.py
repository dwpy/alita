import time
from importlib import import_module
from alita.base import BaseMiddleware
from alita.contrib.sessions.utils import http_date


class SessionMiddleware(BaseMiddleware):
    def __init__(self, app):
        super(SessionMiddleware, self).__init__(app)
        self.engine = import_module(self.app.session_engine)
        self.session_manager = self.engine.SessionManager(app)

    async def process_request(self, request):
        request.session = await self.session_manager.get_session(request)
        request.session_manager = self.session_manager

    async def process_response(self, request, response):
        try:
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            pass
        else:
            if self.app.session_cookie_name in request.cookies and empty and modified:
                response.delete_cookie(
                    self.app.session_cookie_name,
                    path=self.app.session_cookie_path,
                    domain=self.app.session_cookie_domain,
                )
            else:
                if (modified or self.app.session_save_every_request) and not empty:
                    if self.app.config.get("SESSION_EXPIRE_AT_BROWSER_CLOSE", False):
                        max_age = None
                        expires = None
                    else:
                        max_age = self.session_manager.get_expiry_age(request.session)
                        expires_time = time.time() + max_age
                        expires = http_date(expires_time)
                    if isinstance(response, self.app.response_class) \
                            and response.status != 500:
                        await self.session_manager.save_session(request)
                        response.set_cookie(
                            self.app.session_cookie_name,
                            self.session_manager.get_session_id(request),
                            max_age=max_age, expires=expires,
                            path=self.app.session_cookie_path,
                            domain=self.app.session_cookie_domain,
                            secure=self.app.config.get('SESSION_COOKIE_SECURE'),
                            httponly=self.app.config.get('SESSION_COOKIE_HTTPONLY'),
                            samesite=self.app.config.get('SESSION_COOKIE_SAMESITE'),
                        )
        return response
