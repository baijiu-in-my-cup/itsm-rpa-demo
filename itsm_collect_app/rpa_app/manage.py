import asyncio
from concurrent.futures import ThreadPoolExecutor, Future, CancelledError
from typing import Optional, Callable, Coroutine, Any
from itsm_collect_app.rpa_app.handler import Handler
from itsm_collect_app.rpa_app.errors import IgnoreError
from itsm_collect_app.settings import Config
from itsm_collect_app.infrastructure.sql_api import SqlApi
from loguru import logger


class RpaManage:
    def __init__(self, sql_api: SqlApi, config: Config, handle_rpa_exception: Callable[..., Coroutine[Any, Any, Any]]):
        self.sql_api = sql_api
        self.config = config
        self.handle_rpa_exception = handle_rpa_exception
        self.ack_run_time_to_day=False
        self.running = False
        self.flet_loop = asyncio.get_running_loop()
        self._rpa_handler = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='RPA')

    async def _rpa_start(self):
        async with Handler(self.sql_api, self.config) as self._rpa_handler:
            await self._rpa_handler.val_login()
            # while self.running:
            while self._rpa_handler:
                try:
                    await self._rpa_handler.run(
                        ack_run_time_to_day=self.ack_run_time_to_day
                    )
                except IgnoreError:
                    ...

    def _start(self):
        def handler(loop, context):
            _ = context["exception"]
            ...

        loop = asyncio.windows_events.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(handler)
        try:
            loop.run_until_complete(self._rpa_start())
        finally:
            loop.stop()
            loop.close()
            self._rpa_handler = None
            self.running = False

    def _rpa_done_callback(self, future: Future):
        exception = future.exception()
        asyncio.run_coroutine_threadsafe(self.handle_rpa_exception(exception), self.flet_loop)

    async def start(self, ack_run_time_to_day: bool = False):
        self.running = True
        self.ack_run_time_to_day = ack_run_time_to_day
        future = self._executor.submit(self._start)
        future.add_done_callback(self._rpa_done_callback)

    async def stop(self):
        if self._rpa_handler:
            await self._rpa_handler.stop()
