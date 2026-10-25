from playwright.async_api import async_playwright, BrowserContext, APIResponse
from playwright.async_api import expect as pw_expect
from typing import Callable, Coroutine,Tuple
from itsm_collect_app.settings import Config
from itsm_collect_app.rpa_app import errors
import ddddocr
from loguru import logger
from itsm_collect_app.rpa_app.common import create_file_name, load_data_from_file
from itsm_collect_app.schema import *
import re
import time, os
import base64
import asyncio
from playwright._impl._errors import TargetClosedError
from playwright.async_api import TimeoutError as PWTimeoutError

info_file_log = logger.bind(name="info_file_log")
error_file_log = logger.bind(name="error_file_log")
flet_app_log=logger.bind(name="flet_app_log")
pw_expect.set_options(timeout=3000)

class PwApi:

    @staticmethod
    async def get_group_data(driver: 'PwDriver') -> Optional[GroupJson]:
        return await driver.get_group_data()

    @staticmethod
    async def goto_task_page(driver: 'PwDriver', order: GroupData) -> Optional[List[TrackTrace]]:
        return await driver.goto_task_page(order)

    @staticmethod
    async def goto_view_page(driver: 'PwDriver',business_key:str) -> Optional[Tuple[GroupData,List[TrackTrace]]]:
        return await driver.goto_view_page(business_key)

    @staticmethod
    async def wait_for_timeout(driver: 'PwDriver', sleep_time: int = 10) -> None:
        await driver.wait_for_timeout(sleep_time)

    @staticmethod
    async def get_file_list(driver: 'PwDriver', business_key: str) -> Optional[FileListJson]:
        return await driver.get_file_list(business_key)

    @staticmethod
    async def submit(driver: 'PwDriver', submit_person: Person, submit_reply: str) -> Optional[str]:
        return await driver.submit(submit_person, submit_reply)

    @staticmethod
    async def get_feed_list(driver: 'PwDriver', business_key: str) -> Optional[FeedJson]:
        return await driver.get_feed_list(business_key)



class PwDriver:
    def __init__(self,config:Config,headless: bool = False):
        self.config=config
        self.headless = headless
        self.storage_state_path=os.path.join(self.config.app.rpa_dir,f'storage-state-{self.config.itsm.user}.json')

    async def __aenter__(self) -> 'PwDriver':
        self.p = await async_playwright().start()
        launch_kwargs = {'headless': self.headless, 'args': ['--start-maximized']}
        # 若配置了本机浏览器路径则优先使用(channel=chrome),否则回退到 playwright 自带 Chromium
        exec_path = self.config.app.executable_path
        if exec_path and os.path.exists(exec_path):
            launch_kwargs.update({'channel': 'chrome', 'executable_path': exec_path})
        self.browser = await self.p.chromium.launch(**launch_kwargs)
        self.context = await self.new_context()
        self.page = await self.context.new_page()
        # self.browser = await self.p.chromium.connect_over_cdp(cdp_url)
        # self.context = self.browser.contexts[0]
        self.stop = self.__aexit__
        self.page = self.context.pages[0]
        return self

    async def add_cookies(self) -> None:
        if os.path.exists(self.storage_state_path) is False:
            return
        flet_app_log.debug(f'从{self.storage_state_path}载入登录状态')
        data = load_data_from_file(self.storage_state_path)
        await self.context.add_cookies(data.get('cookies', []))

    async def start(self) -> 'PwDriver':
        return await self.__aenter__()

    async def __aexit__(self, *args: Any) -> None:
        try:
            await self.browser.close()
            await self.p.stop()
        except Exception as e:
            pass

    async def new_context(self) -> BrowserContext:
        context_data = {}
        if os.path.exists(self.storage_state_path):
            flet_app_log.debug(f'从{self.storage_state_path}载入登录状态')
            context_data['storage_state'] = self.storage_state_path
        context = await self.browser.new_context(**context_data,no_viewport=True)
        return context

    async def get_login_code(self) -> str:
        yzm_path = os.path.join(self.config.app.screenshots_path, 'yzm.png')
        await self.page.locator('#valImg').first.screenshot(path=yzm_path)
        ocr = ddddocr.DdddOcr(show_ad=False)
        with open(yzm_path, 'rb') as f:
            img_bytes = f.read()
        yzm = ocr.classification(img_bytes)
        return yzm

    async def _login(self,index_url:str):
        # 这里可能需要一个等待
        if self.config.itsm.name == 'support-agent':
            try:
                await self.page.wait_for_selector('//*[@id="loginForm"]//input[@id="staffId"]', timeout=5000)
            except (TimeoutError, PWTimeoutError):
                return
            await self.page.locator('//*[@id="loginForm"]//input[@id="staffId"]').first.fill(self.config.itsm.user)
            await self.page.locator('//*[@id="loginForm"]//input[@id="staffPwd"]').first.fill(self.config.itsm.pwd)
            yzm = await self.get_login_code()

            await self.page.locator('//*[@id="loginForm"]//input[@id="validCode"]').first.fill(yzm)
            await self.page.locator('//*[@id="loginForm"]//*[@id="btnSubmit"]').first.click()
            try:
                await self.page.wait_for_selector('//*[@id="loginForm"]//*[@id="loginPrompt"]', timeout=2500)
            except (TimeoutError, PWTimeoutError):
                try:
                    await self.page.wait_for_url(index_url)
                except (TimeoutError, PWTimeoutError):
                    flet_app_log.debug('itsm 登录错误')
                    pic_path = os.path.join(self.config.app.screenshots_path, create_file_name('png'))
                    await self.page.screenshot(path=pic_path, full_page=True)
                    raise errors.LoginError('itsm login error')
            else:
                login_msg = await self.page.locator('//*[@id="loginForm"]//*[@id="loginPrompt"]').inner_text()
                if '验证码错误' in login_msg:
                    raise errors.YzmError('验证码错误')
                elif '用户名或密码错误' in login_msg:
                    raise errors.PwdError('用户名或密码错误')
        else:
            while True:
                try:
                    await pw_expect(self.page).to_have_url(index_url)
                except AssertionError:
                    pass
                else:
                    return

    async def login(self) -> None:
        # await self.add_cookies()
        flet_app_log.debug(f'开始登录')
        _, index_url = self.config.itsm.format_index_url()
        await self.page.goto(index_url)
        await self.val_login(index_url)

    async def val_login(self, index_url: str) -> None:
        await self.page.reload()
        while True:
            try:
                await pw_expect(self.page).to_have_url(index_url)
            except AssertionError:
                try:
                    await self._login(index_url)
                except errors.YzmError:
                    pass
            else:
                await self.context.storage_state(path=self.storage_state_path)
                flet_app_log.debug('登录成功')
                return

    async def requests(self, method: str) -> Callable[..., Coroutine[Any, Any, 'APIResponse']]:
        if method == "POST":
            return self.page.request.post
        elif method == "GET":
            return self.page.request.get
        raise ValueError(f"Unsupported method: {method}")

    async def get_group_data(self, ) -> GroupJson:
        request_start = time.time()
        method, url = self.config.itsm.format_gro_url()
        try:
            request_method = await self.requests(method)
            response = await request_method(url)
            flet_app_log.debug(f'request to {response.url} take {time.time() - request_start:.2f} seconds')
            if not response.ok:
                raise Exception(await response.body())
            json_data = GroupJson(**await response.json())
            return json_data
        except Exception as e:
            error_file_log.exception(e)
            raise e

    async def wait_for_timeout(self, sleep_time: int = 10):
        await self.page.wait_for_timeout(sleep_time * 1000)


    async def goto_view_page(self,business_key:str)->Tuple[GroupData,List[TrackTrace]]:
        try:
            _,url=self.config.itsm.format_view_business_info(business_key)
            await self.page.goto(url)
            await self.page.wait_for_url(url)
            title_text=await self.page.locator('//td[text()="需求标题"]/following-sibling::td[1]').inner_text()
            desc_text = await self.page.locator('//td[text()="需求描述"]/following-sibling::td[1]').inner_text()
            gourp_data=GroupData(business_key=business_key.strip(),worksheet_desc=desc_text.strip(),worksheet_title=title_text.strip())
            table_data=await self._get_table_data()
            return gourp_data,table_data
        except Exception as e:
            error_file_log.exception(e)
            raise errors.DriverApiError(e)

    async def _get_table_data(self)-> List[TrackTrace]:
        table = self.page.locator('//*[@id="bigtabel1"]//table[@id="example-advanced"]')
        header_cells = await table.locator('xpath=.//thead/tr/th').all_inner_texts()
        header_cells = [header.strip() for header in header_cells]

        table_data = []
        rows = await table.locator('xpath=.//tbody/tr').all()
        for tr in rows[:-1]:
            body_cells = await tr.locator('xpath=./td').all_inner_texts()
            body_cells = [re.sub(r'^\s+|\s+$', '', text) for text in body_cells]
            table_data.append({k: v for k, v in zip(header_cells, body_cells)})
        return [TrackTrace.model_validate(row) for row in table_data]

    async def goto_task_page(self, order: GroupData) -> List[TrackTrace]:
        try:
            _, url = self.config.itsm.format_task_info_id_url(order.task_info_id)
            await self.page.goto(url)
            await self.page.wait_for_url(url)
            await pw_expect(self.page).not_to_have_title('提示 - ITSM系统')
            desc_text = await self.page.locator('//td[text()="需求描述"]/following-sibling::td[1]').inner_text()
            order.worksheet_desc = desc_text.strip()
            return await self._get_table_data()
        except Exception as e:
            error_file_log.exception(e)
            raise errors.DriverApiError(e)

    async def get_file_list(self, business_key: str) -> FileListJson:
        request_start = time.time()
        method, url = self.config.itsm.format_get_file_list_url(business_key)
        try:
            request_method = await self.requests(method)
            response = await request_method(url)
            logger.debug(f'request to {response.url} take {time.time() - request_start:.2f} seconds')
            if not response.ok:
                raise Exception(await response.body())
            json_data = FileListJson(**await response.json())
            return json_data
        except Exception as e:
            error_file_log.exception(e)
            raise errors.DriverApiError(e)

    async def get_feed_list(self,business_key: str) -> Optional[FeedJson]:
        request_start = time.time()
        method, url = self.config.itsm.format_get_feed_url(business_key)
        try:
            request_method = await self.requests(method)
            response = await request_method(url)
            logger.debug(f'request to {response.url} take {time.time() - request_start:.2f} seconds')
            if not response.ok:
                raise Exception(await response.body())
            json_data = FeedJson(**await response.json())
            return json_data
        except Exception as e:
            error_file_log.exception(e)
            raise errors.DriverApiError(e)

    async def submit(self, submit_person: Person, submit_reply: str) -> Optional[str]:
        # 与本地 Mock ITSM 的提交弹窗配合: 点击“提交” -> 操作命名 iframe 选部门/处理人/填写意见 -> 确认
        try:
            await self.page.locator('//*[@data-operation-type="提交"]').click()
            await self.page.wait_for_timeout(500)
            frame = self.page.frame(name="submit-frame")
            if frame is None:
                raise Exception('submit frame not found')
            # 选择提交部门(逐级)
            for department in submit_person.department:
                await frame.locator(f'//a[@data-dept="{department}"]').click()
                await self.page.wait_for_timeout(200)
            # 双击选择处理人
            await frame.locator(
                f'//ul[@id="userList"]//span[@data-user="{submit_person.name}"]').dblclick()
            await self.page.wait_for_timeout(200)
            selected = await frame.locator('#selectedHandler').inner_text()
            if selected.strip() != submit_person.name:
                error_file_log.warning(f'处理人选择错误: 期望{submit_person.name} 实际{selected}')
                raise Exception('submit handler select error')
            # 填写处理意见
            await frame.locator('#dealOpinion').fill(submit_reply)
            # 确认提交
            await frame.locator('#confirmSubmit').click()
            info_file_log.info(f'提交【{submit_person.name}】')
            flet_app_log.success(f'提交【{submit_person.name}】')
            await self.page.wait_for_timeout(800)
            await self.page.reload()
        except Exception as e:
            error_file_log.exception(f'transfer error:{e}')
            raise errors.XpathError(e)
