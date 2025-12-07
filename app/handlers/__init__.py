from aiogram import Router
from .common import router as common_router

def get_routers() -> list[Router]:
    return [common_router]
