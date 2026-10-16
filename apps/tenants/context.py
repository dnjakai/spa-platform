"""
The tenant for the current request or job.

A ContextVar (not a thread-local) so it is also correct under ASGI and in
async tasks. TenantMiddleware sets it per request; background jobs and
management commands use `tenant_context(tenant)`.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_current_tenant = ContextVar("current_tenant", default=None)


def get_current_tenant():
    return _current_tenant.get()


def set_current_tenant(tenant):
    """Set the tenant and return a token for `reset_current_tenant`."""
    return _current_tenant.set(tenant)


def reset_current_tenant(token):
    _current_tenant.reset(token)


@contextmanager
def tenant_context(tenant):
    token = set_current_tenant(tenant)
    try:
        yield tenant
    finally:
        reset_current_tenant(token)
