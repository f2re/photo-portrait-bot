"""
Handlers package
"""
from . import user, admin, payment, support, batch_processing


def get_routers():
    """
    Get all routers in the correct order.
    IMPORTANT: batch_processing must be registered BEFORE user router
    to handle media groups (albums) before single images.
    """
    return [
        batch_processing.router,
        user.router,
        admin.router,
        payment.router,
        support.router,
    ]