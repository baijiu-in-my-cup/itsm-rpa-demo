from loguru import logger
from itsm_collect_app.schema import *
from itsm_collect_app.rpa_app.common import str_match,str_match_enhance

flet_app_log = logger.bind(name="flet_app_log")



class EvaluateMachine:
    def __init__(self, work_sheet: GroupData, track_trace_rows: List[TrackTrace], file_rows: List[FileRow],feed_rows:List[FeedRow]):
        self.business_key = work_sheet.business_key
        self.track_trace_rows = track_trace_rows
        self.file_rows = file_rows
        self.work_sheet = work_sheet
        self.feed_rows=feed_rows

    async def file_filter_content_evaluate(self, filter_content: FileFilterContent, ) -> bool:
        match_files = []
        for file in self.file_rows:
            if [file_key for file_key in filter_content.file_key if
                file_key in file.file_name]:
                match_files.append(file.file_type)

        if match_files:
            if filter_content.file_type:
                match_files = [file_type for file_type in match_files if file_type in filter_content.file_type]
                if not match_files:
                    return False if filter_content.is_or_not else True
            if filter_content.file_len and len(match_files) != filter_content.file_len:
                return False if filter_content.is_or_not else True
            return True if filter_content.is_or_not else False
        return False if filter_content.is_or_not else True
    async def feed_filter_content_evaluate(self,filter_content: FeedFilterContent):
        alias_dict = {k: v.alias for k, v in filter_content.__fields__.items()}
        for index, feed_row in enumerate(self.feed_rows):
            logger.debug(f'Start Track Trace Row-{index}----------------')
            filter_content_dict = filter_content.model_dump(exclude={'filter_desc', 'is_or_not', 'str_fuzzy_match_key'})
            feed_row_dict = feed_row.model_dump()
            results = []
            for k, v in filter_content_dict.items():
                if not v:
                    continue
                if alias_dict.get(k, k) in filter_content.str_fuzzy_match_key:
                    result = str_match_enhance(v, feed_row_dict[k], strict=False)
                else:
                    result = str_match_enhance(v, feed_row_dict[k], strict=True)
                if result is False and filter_content.is_or_not is True:
                    break
                results.append(result)
            else:
                if results and all(results):
                    return True if filter_content.is_or_not else False

        return False if filter_content.is_or_not else True

    async def track_trace_filter_content_evaluate(self, filter_content: TrackTraceFilterContent) -> bool:
        alias_dict = {k:v.alias for k, v in filter_content.__fields__.items()}
        for index, track_trace in enumerate(self.track_trace_rows):
            logger.debug(f'Start Track Trace Row-{index}----------------')
            filter_content_dict = filter_content.model_dump(exclude={'filter_desc', 'is_or_not','str_fuzzy_match_key'})
            track_trace_dict = track_trace.model_dump()
            results = []
            for k, v in filter_content_dict.items():
                if not v:
                    continue
                if alias_dict.get(k,k) in filter_content.str_fuzzy_match_key:
                    result = str_match(v, track_trace_dict[k],strict=False)
                else:
                    result = str_match(v, track_trace_dict[k], strict=True)
                if result is False and filter_content.is_or_not is True:
                    break
                results.append(result)
            else:
                if results and all(results):
                    return True if filter_content.is_or_not else False

        return False if filter_content.is_or_not else True

    async def work_sheet_filter_content_evaluate(self, filter_content: WorkSheetFilterContent) -> bool:
        filter_content_dict = filter_content.model_dump(exclude={'filter_desc', 'is_or_not', 'str_fuzzy_match_key'})
        work_sheet_dict = self.work_sheet.model_dump()
        results = []
        for k, v in filter_content_dict.items():
            if not v:
                continue
            results.append(str_match(v, work_sheet_dict[k], strict=True))
        if all(results):
            return True if filter_content.is_or_not else False
        return False if filter_content.is_or_not else True

    async def filter_content_splitter(self, task_desc: str, condition: Union[
        FileFilterContent, TrackTraceFilterContent, WorkSheetFilterContent]) -> bool:
        is_or_not_to_desc_dict={
            True:'存在',False:'不存在'
        }
        result = False
        filter_content=condition.model_dump(exclude={'filter_desc','is_or_not'},by_alias=True,exclude_none=True)
        if isinstance(condition, FileFilterContent):
            result = await self.file_filter_content_evaluate(condition)
        if isinstance(condition, TrackTraceFilterContent):
            result = await self.track_trace_filter_content_evaluate(condition)
        if isinstance(condition, WorkSheetFilterContent):
            result = await self.work_sheet_filter_content_evaluate(condition)
        if isinstance(condition,FeedFilterContent):
            result = await self.feed_filter_content_evaluate(condition)
        flet_app_log.debug(f'【{self.business_key}】【{task_desc}】-{is_or_not_to_desc_dict[condition.is_or_not]}{condition.filter_desc}-{filter_content} 判断结果 :{result}')
        return result

    async def recursive_evaluate(
            self, task_desc: str, condition: Any
    ) -> bool:
        if type(condition) in (FileFilterContent, TrackTraceFilterContent, WorkSheetFilterContent,FeedFilterContent):
            return await self.filter_content_splitter(task_desc, condition)
        if isinstance(condition, FilterContent):
            results = []
            for sub_filter in condition.filter_content:
                result = await self.recursive_evaluate(task_desc, sub_filter)
                if condition.filter_type == 'or' and result is True:
                    return result
                if condition.filter_type == 'and' and result is False:
                    return result
                results.append(result)
            return all(results)
        ValueError('Invalid Recursive Type')
