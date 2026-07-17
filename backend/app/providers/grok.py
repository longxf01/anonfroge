from __future__ import annotations

from typing import Any

from app.core.base_provider import BaseProvider


PROVIDER_CONFIG = {'key': 'grok',
 'protocol': 'openai',
 'version': '1.0',
 'name': 'grok',
 'description': '',
 'decs_url': 'https://api.x.ai/v1',
 'icon': '',
 'inputs': [{'key': 'api_key', 'label': 'key', 'type': 'password', 'required': True}],
 'input_values': {'api_key': 'enc:v1:Fl2Ex-nC0jXsuNenF_p4zaQLjXDkSKOf6YSB7aDHBnQ8hcpJClVVe3y5DGyNm-cqVKi3d1pbXBvIy1uuvWokMwEHJYV6EkpGSRpsuqyyqJJm'},
 'base_url': 'https://mskxaigrok.nds.kdns.fr:8443/v1',
 'enabled': True,
 'sort_order': 0,
 'models': [{'name': 'grok-4.5',
             'model_id': 'grok-4.5',
             'model_type': 'text',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-4.5',
                            'object': 'model',
                            'created': 1784106412,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []},
            {'name': 'grok-4.20-0309',
             'model_id': 'grok-4.20-0309',
             'model_type': 'text',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-4.20-0309',
                            'object': 'model',
                            'created': 1784100185,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []},
            {'name': 'grok-4.20-0309-non-reasoning',
             'model_id': 'grok-4.20-0309-non-reasoning',
             'model_type': 'text',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-4.20-0309-non-reasoning',
                            'object': 'model',
                            'created': 1784100185,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []},
            {'name': 'grok-4.20-0309-reasoning',
             'model_id': 'grok-4.20-0309-reasoning',
             'model_type': 'text',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-4.20-0309-reasoning',
                            'object': 'model',
                            'created': 1784100185,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []},
            {'name': 'grok-4.20-multi-agent-0309',
             'model_id': 'grok-4.20-multi-agent-0309',
             'model_type': 'text',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-4.20-multi-agent-0309',
                            'object': 'model',
                            'created': 1784100185,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []},
            {'name': 'grok-4.3',
             'model_id': 'grok-4.3',
             'model_type': 'text',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-4.3',
                            'object': 'model',
                            'created': 1784100185,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []},
            {'name': 'grok-build-0.1',
             'model_id': 'grok-build-0.1',
             'model_type': 'text',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-build-0.1',
                            'object': 'model',
                            'created': 1784100185,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []},
            {'name': 'grok-chat-fast',
             'model_id': 'grok-chat-fast',
             'model_type': 'text',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-chat-fast',
                            'object': 'model',
                            'created': 1784100185,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []},
            {'name': 'grok-imagine-image',
             'model_id': 'grok-imagine-image',
             'model_type': 'image',
             'description': 'grok2api',
             'modes': ['text'],
             'think': False,
             'voices': [],
             'audio': None,
             'duration_resolution_map': [],
             'raw_config': {'id': 'grok-imagine-image',
                            'object': 'model',
                            'created': 1784100185,
                            'owned_by': 'grok2api'},
             'aspect_ratios': [],
             'sizes': [],
             'fps': []}],
 'url': 'https://api.x.ai/v1'}


class Text(BaseProvider):
    provider_key = PROVIDER_CONFIG["key"]
    provider_config = PROVIDER_CONFIG
    model_type = "text"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_text(model_id=model_id, **kwargs)

    async def generate_text(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise NotImplementedError("请实现当前服务的文本生成逻辑")


class Image(BaseProvider):
    provider_key = PROVIDER_CONFIG["key"]
    provider_config = PROVIDER_CONFIG
    model_type = "image"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_image(model_id=model_id, **kwargs)

    async def generate_image(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise NotImplementedError("请实现当前服务的图像生成逻辑")


class Video(BaseProvider):
    provider_key = PROVIDER_CONFIG["key"]
    provider_config = PROVIDER_CONFIG
    model_type = "video"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_video(model_id=model_id, **kwargs)

    async def generate_video(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise NotImplementedError("请实现当前服务的视频生成逻辑")


class TTS(BaseProvider):
    provider_key = PROVIDER_CONFIG["key"]
    provider_config = PROVIDER_CONFIG
    model_type = "tts"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_tts(model_id=model_id, **kwargs)

    async def generate_tts(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise NotImplementedError("请实现当前服务的语音生成逻辑")