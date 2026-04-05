"""Uvicorn integration: colored logging and sync/async ``run`` for Server."""

from __future__ import annotations

import logging
from typing import Any, Optional

import uvicorn

from jvspatial.logging import configure_standard_logging


class _LevelColorFormatter(logging.Formatter):
    """Colorize only the level name to match jvspatial console format."""

    _LEVEL_COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m\033[97m",  # White on red background
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        color = self._LEVEL_COLORS.get(record.levelname, "")
        original_levelname = record.levelname
        if color:
            record.levelname = f"{color}{record.levelname}{self._RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


class ServerRunMixin:
    """``run`` / ``run_async`` using Uvicorn and shared log formatting."""

    def run(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: Optional[bool] = None,
        app_path: Optional[str] = None,
        **uvicorn_kwargs: Any,
    ) -> None:
        """Run the server using uvicorn.

        Args:
            host: Override host address
            port: Override port number
            reload: Enable auto-reload for development
            app_path: Import string for the ASGI app, e.g. ``"app.main:app"``.
                Required when ``reload=True`` so uvicorn can re-import the
                module in each reload worker.  When omitted and reload is
                enabled a warning is logged and the app object is used
                directly (reload will not work correctly).
            **uvicorn_kwargs: Additional uvicorn parameters
        """
        configure_standard_logging(
            level=self.config.log_level,
            enable_colors=True,
            preserve_handler_class_names=["DBLogHandler", "StartupLogCounter"],
        )

        run_host = host or self.config.host
        run_port = port or self.config.port
        run_reload = reload if reload is not None else self.config.debug

        server_info = f"http://{run_host}:{run_port}"
        if self.config.docs_url:
            server_info += f" | docs: {self.config.docs_url}"
        self._logger.info(f"🔧 Server: {server_info}")

        formatter = _LevelColorFormatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )

        uvicorn_config = {
            "host": run_host,
            "port": run_port,
            "reload": run_reload,
            "log_level": self.config.log_level,
            "log_config": {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "()": _LevelColorFormatter,
                        "fmt": formatter._fmt,
                        "datefmt": formatter.datefmt,
                    }
                },
                "handlers": {
                    "default": {
                        "class": "logging.StreamHandler",
                        "formatter": "default",
                        "stream": "ext://sys.stdout",
                    }
                },
                "loggers": {
                    "uvicorn": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                    "uvicorn.error": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                    "uvicorn.access": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                },
            },
            **uvicorn_kwargs,
        }

        if run_reload and app_path:
            uvicorn.run(app_path, **uvicorn_config)
        else:
            if run_reload and not app_path:
                self._logger.warning(
                    "reload=True but no app_path provided; reload workers will "
                    "not re-register endpoints correctly.  Pass "
                    'app_path="module:app" to run() to fix this.'
                )
            app = self.get_app()
            uvicorn.run(app, **uvicorn_config)

    async def run_async(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        **uvicorn_kwargs: Any,
    ) -> None:
        """Run the server asynchronously.

        Args:
            host: Override host address
            port: Override port number
            **uvicorn_kwargs: Additional uvicorn parameters
        """
        run_host = host or self.config.host
        run_port = port or self.config.port

        app = self.get_app()

        formatter = _LevelColorFormatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )

        config = uvicorn.Config(
            app,
            host=run_host,
            port=run_port,
            log_level=self.config.log_level,
            log_config={
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "()": _LevelColorFormatter,
                        "fmt": formatter._fmt,
                        "datefmt": formatter.datefmt,
                    }
                },
                "handlers": {
                    "default": {
                        "class": "logging.StreamHandler",
                        "formatter": "default",
                        "stream": "ext://sys.stdout",
                    }
                },
                "loggers": {
                    "uvicorn": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                    "uvicorn.error": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                    "uvicorn.access": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                },
            },
            **uvicorn_kwargs,
        )
        server = uvicorn.Server(config)
        await server.serve()
