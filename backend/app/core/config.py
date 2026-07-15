from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.core.tasks.constants import (
    DEFAULT_ASYNC_TASK_MODULES,
    DEFAULT_IMAGE_GENERATION_TIMEOUT_SECONDS,
    DEFAULT_MEDIA_GENERATION_MAX_CONCURRENCY,
    DEFAULT_MEDIA_GENERATION_POLL_INTERVAL_SECONDS,
    DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS,
    DEFAULT_TASK_CONSUMER_GROUP,
    DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS,
    DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS,
    DEFAULT_TASK_STREAM_MAX_LEN,
    DEFAULT_TASK_STREAM_NAME,
    DEFAULT_TASK_WORKER_BATCH_SIZE,
    DEFAULT_TASK_WORKER_BLOCK_MS,
    DEFAULT_TASK_WORKER_CONSUMER_NAME,
    DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS,
    DEFAULT_TASK_WORKER_LOG_ENABLED,
    DEFAULT_TASK_WORKER_MAX_CONCURRENCY,
    DEFAULT_TASK_WORKER_MAX_RETRIES,
    DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS,
    DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS,
    DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS,
    DEFAULT_VIDEO_GENERATION_TIMEOUT_SECONDS,
)

# 提取项目工程的根目录路径，拼接.env的路径并加载.env中的环境配置
BASE_DIR = Path(__file__).resolve().parents[3]

# 拼接路径
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE, override=False)


def _env_bool(name: str, default: bool) -> bool:
    """从环境变量解析布尔值。"""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


# frozen=True 冻结属性值，不允许配置类Settings实例化以后，被其他地方的程序修改属性值
@dataclass(frozen=True)
class Settings(object):
    """项目运行时配置对象。"""
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "App"))  # 应用名称
    app_description: str = field(default_factory=lambda: os.getenv("APP_DESCRIPTION", "App description"))  # 应用描述
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))  # 应用运行环境
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))  # 后端监听地址
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))  # 后端监听端口
    api_prefix: str = field(default_factory=lambda: os.getenv("API_PREFIX", "/api"))  # API 路由前缀
    oss_root: str = field(default_factory=lambda: os.getenv("OSS_ROOT", "./data/oss"))  # 本地 OSS 根目录
    db_engine: str = field(default_factory=lambda: os.getenv("DB_ENGINE", "postgres"))  # 数据库类型
    db_driver: str = field(default_factory=lambda: os.getenv("DB_DRIVER", "psycopg"))  # 数据库驱动
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "127.0.0.1"))  # 数据库主机
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))  # 数据库端口
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", "anonforge"))  # 数据库名称
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "anonforge"))  # 数据库用户名
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", "anonforge"))  # 数据库密码
    db_sqlite_path: str = field(default_factory=lambda: os.getenv("DB_SQLITE_PATH", "./data/app.db"))  # SQLite 数据库文件路径
    tz: str = field(default_factory=lambda: os.getenv("TZ", "Asia/Shanghai"))  # 默认时区
    postgres_image: str = field(default_factory=lambda: os.getenv("POSTGRES_IMAGE", "postgres:18-alpine"))  # PostgreSQL 容器镜像
    postgres_container_name: str = field(default_factory=lambda: os.getenv("POSTGRES_CONTAINER_NAME", "anonforge_dev_postgres"))  # PostgreSQL 容器名称
    postgres_host_port: int = field(default_factory=lambda: int(os.getenv("POSTGRES_HOST_PORT", "5432")))  # PostgreSQL 宿主机端口
    db_data_path: str = field(default_factory=lambda: os.getenv("DB_DATA_PATH", "./postgres/data"))  # 数据库数据目录
    db_healthcheck_interval: str = field(default_factory=lambda: os.getenv("DB_HEALTHCHECK_INTERVAL", "10s"))  # 数据库健康检查间隔
    db_healthcheck_timeout: str = field(default_factory=lambda: os.getenv("DB_HEALTHCHECK_TIMEOUT", "5s"))  # 数据库健康检查超时
    db_healthcheck_retries: int = field(default_factory=lambda: int(os.getenv("DB_HEALTHCHECK_RETRIES", "5")))  # 数据库健康检查重试次数

    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "127.0.0.1"))  # Redis 主机
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))  # Redis 端口
    redis_db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))  # Redis 数据库编号
    redis_container_name: str = field(default_factory=lambda: os.getenv("REDIS_CONTAINER_NAME", "anonforge_dev_redis"))  # Redis 容器名称
    redis_data_path: str = field(default_factory=lambda: os.getenv("REDIS_DATA_PATH", "./redis/data"))  # Redis 数据目录
    redis_healthcheck_interval: str = field(default_factory=lambda: os.getenv("REDIS_HEALTHCHECK_INTERVAL", "10s"))  # Redis 健康检查间隔
    redis_healthcheck_timeout: str = field(default_factory=lambda: os.getenv("REDIS_HEALTHCHECK_TIMEOUT", "5s"))  # Redis 健康检查超时
    redis_healthcheck_retries: int = field(default_factory=lambda: int(os.getenv("REDIS_HEALTHCHECK_RETRIES", "3")))  # Redis 健康检查重试次数

    redis_token_key_prefix: str = field(default_factory=lambda: os.getenv("REDIS_TOKEN_KEY_PREFIX", "auth:token:"))  # Redis 令牌缓存键前缀
    redis_task_stream_name: str = field(default_factory=lambda: os.getenv("REDIS_TASK_STREAM_NAME", DEFAULT_TASK_STREAM_NAME))  # 异步任务 Redis Stream 名称
    redis_task_consumer_group: str = field(default_factory=lambda: os.getenv("REDIS_TASK_CONSUMER_GROUP", DEFAULT_TASK_CONSUMER_GROUP))  # 异步任务 Redis Stream 消费组
    redis_task_stream_max_len: int = field(default_factory=lambda: int(os.getenv("REDIS_TASK_STREAM_MAX_LEN", DEFAULT_TASK_STREAM_MAX_LEN)))  # 异步任务 Redis Stream 最大保留长度
    async_task_modules: tuple[str, ...] = field( default_factory=lambda: tuple( item.strip() for item in os.getenv("ASYNC_TASK_MODULES", ",".join(DEFAULT_ASYNC_TASK_MODULES)).split(",") if item.strip() ) )  # 异步任务业务模块列表
    async_task_worker_consumer_name: str = field(default_factory=lambda: os.getenv("ASYNC_TASK_WORKER_CONSUMER_NAME", DEFAULT_TASK_WORKER_CONSUMER_NAME))  # 异步任务 Worker 消费者名称
    async_task_worker_batch_size: int = field(default_factory=lambda: int(os.getenv("ASYNC_TASK_WORKER_BATCH_SIZE", DEFAULT_TASK_WORKER_BATCH_SIZE)))  # 异步任务 Worker 单批读取数量
    async_task_worker_block_ms: int = field(default_factory=lambda: int(os.getenv("ASYNC_TASK_WORKER_BLOCK_MS", DEFAULT_TASK_WORKER_BLOCK_MS)))  # 异步任务 Worker 阻塞读取毫秒数
    async_task_worker_idle_sleep_seconds: float = field( default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_IDLE_SLEEP_SECONDS", DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS)) )  # 异步任务 Worker 空闲休眠秒数
    async_task_worker_max_concurrency: int = field(default_factory=lambda: int(os.getenv("ASYNC_TASK_WORKER_MAX_CONCURRENCY", DEFAULT_TASK_WORKER_MAX_CONCURRENCY)))  # 异步任务 Worker 最大并发处理数量
    async_task_worker_task_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_TASK_TIMEOUT_SECONDS", DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS)))  # 异步任务单个子项执行超时秒数
    async_task_worker_log_enabled: bool = field(default_factory=lambda: _env_bool("ASYNC_TASK_WORKER_LOG_ENABLED", DEFAULT_TASK_WORKER_LOG_ENABLED))  # 异步任务 Worker 是否打印任务执行日志
    async_task_worker_heartbeat_interval_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS", DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS)))  # 异步任务 Worker 心跳刷新间隔秒数
    async_task_worker_max_retries: int = field(default_factory=lambda: int(os.getenv("ASYNC_TASK_WORKER_MAX_RETRIES", DEFAULT_TASK_WORKER_MAX_RETRIES)))  # 异步任务默认最大重试次数
    async_task_worker_retry_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_RETRY_BACKOFF_SECONDS", DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS)))  # 异步任务重试基础退避秒数
    async_task_worker_shutdown_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS", DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS)))  # 异步任务 Worker 优雅退出等待秒数
    async_task_stale_running_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_STALE_RUNNING_TIMEOUT_SECONDS", DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS)))  # 异步任务运行中状态失联判定秒数
    async_task_orphan_scavenger_interval_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS", DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS)))  # 异步任务孤儿扫描间隔秒数
    algorithm: str = field(default_factory=lambda: os.getenv("ALGORITHM", "HS256"))  # JWT 签名算法
    access_token_expire_seconds: int = field(default_factory=lambda: int(os.getenv("ACCESS_TOKEN_EXPIRE_SECONDS", "900")))  # 访问令牌有效秒数
    refresh_token_expire_seconds: int = field(default_factory=lambda: int(os.getenv("REFRESH_TOKEN_EXPIRE_SECONDS", "604800")))  # 刷新令牌有效秒数
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", "dev-secret-key"))  # 应用密钥

    user_default_admin_name: str = field(default_factory=lambda: os.getenv("USER_DEFAULT_ADMIN_NAME", "admin"))  # 默认管理员用户名
    user_default_admin_password: str = field(default_factory=lambda: os.getenv("USER_DEFAULT_ADMIN_PASSWORD", "admin123"))  # 默认管理员密码

    visual_style_root: str = field(default_factory=lambda: os.getenv("VISUAL_STYLE_ROOT", "./data/skills/art_list"))  # 视觉风格资源根目录
    director_manual_root: str = field(default_factory=lambda: os.getenv("DIRECTOR_MANUAL_ROOT", "./data/skills/director_manual"))  # 导演手册资源根目录
    skills_root: str = field(default_factory=lambda: os.getenv("SKILLS_ROOT", "./data/skills"))  # 技能文档根目录
    chapter_event_extraction_prompt_name: str = field( default_factory=lambda: os.getenv("CHAPTER_EVENT_EXTRACTION_PROMPT_NAME", "chapter_event_extraction") )  # 章节事件提取提示词名称
    
    model_request_timeout_seconds: float = field( default_factory=lambda: float(os.getenv("MODEL_REQUEST_TIMEOUT_SECONDS", "180")) )  # 模型请求超时秒数
    media_generation_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("MEDIA_GENERATION_TIMEOUT_SECONDS", DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS)))  # 媒体生成通用超时秒数
    image_generation_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("IMAGE_GENERATION_TIMEOUT_SECONDS", DEFAULT_IMAGE_GENERATION_TIMEOUT_SECONDS)))  # 图片生成超时秒数
    video_generation_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("VIDEO_GENERATION_TIMEOUT_SECONDS", DEFAULT_VIDEO_GENERATION_TIMEOUT_SECONDS)))  # 视频生成超时秒数
    media_generation_poll_interval_seconds: float = field(default_factory=lambda: float(os.getenv("MEDIA_GENERATION_POLL_INTERVAL_SECONDS", DEFAULT_MEDIA_GENERATION_POLL_INTERVAL_SECONDS)))  # 媒体生成异步轮询间隔秒数
    media_generation_max_concurrency: int = field(default_factory=lambda: int(os.getenv("MEDIA_GENERATION_MAX_CONCURRENCY", DEFAULT_MEDIA_GENERATION_MAX_CONCURRENCY)))  # 媒体生成默认最大并发数量
    provider_template_path: str = field(default_factory=lambda: os.getenv("PROVIDER_TEMPLATE_PATH", "./data/provider_template.py"))  # 服务商模板文件路径

settings = Settings()

def oss_root_path() -> Path:
    """返回 OSS 本地根目录，配置为相对路径时按工程根目录解析。"""
    configured = Path(settings.oss_root).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    return root.resolve()

def project_path(configured_path: str) -> Path:
    """按项目根目录解析配置路径。"""
    configured = Path(configured_path).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    return root.resolve()


def skills_root_path(config: Settings | None = None) -> Path:
    """返回技能文档根目录。"""
    current = config or settings
    return project_path(current.skills_root)
