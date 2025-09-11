from contextvars import ContextVar

user_id_ctx = ContextVar('current_user', default=None)
access_token_ctx = ContextVar('access_token', default=None)