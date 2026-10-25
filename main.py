import json,os
import pathlib

import flet as ft
from itsm_collect_app.desktop_app.app import DesktopApp
import aiosqlite
from sqlalchemy.ext.asyncio import create_async_engine
from itsm_collect_app.infrastructure.database import create_database
from contextlib import asynccontextmanager
from itsm_collect_app.settings import Config
from itsm_collect_app.infrastructure.database import Database
from itsm_collect_app.infrastructure.sql_api import SqlApi
from loguru import logger



def setup_logger(log_path:str):
    logger.remove()
    # logger.add(sys.stderr, level="DEBUG")
    logger.add(log_path + "-info/runtime_{time:YYYY-MM-DD}.log",
            filter=lambda record: record["extra"].get("name", "") == "info_file_log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS}|{message}", rotation="1 MB")

    logger.add(log_path + "-error/runtime_{time:YYYY-MM-DD}.log",
            filter=lambda record: record["extra"].get("name", "") == "error_file_log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS}|{message}", rotation="1 MB")


@asynccontextmanager
async def lifespan(database:'Database'):
    await database.connect()
    yield
    await database.disconnect()

async def main(page: ft.Page):
    config=Config()
    setup_logger(os.path.join(config.app.rpa_dir, 'log'))
    engine = create_async_engine(
        config.app.database_url,
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
        json_deserializer=json.loads,
    )
    database = create_database(engine)
    async with lifespan(database):
        sql_api = SqlApi(database,persons_path=config.app.persons_path,tasks_dir=config.app.tasks_dir)
        await sql_api.load_task_data()
        await sql_api.load_person_data()
        app = DesktopApp(page,sql_api,config)
        await app.build()

if __name__ == "__main__":
    ft.app(target=main)

# ---- 可选:打包为桌面 exe(按需调整路径) ----
# flet pack main.py -n itsm-rpa-demo --add-data=itsm_collect_app\static;itsm_collect_app\static \
#   --add-data=<site-packages>\ddddocr\common_det.onnx:ddddocr \
#   --add-data=<site-packages>\ddddocr\common_old.onnx:ddddocr \
#   --add-data=<site-packages>\ddddocr\common.onnx:ddddocr