import logging
from typing import Any

from dank_mids._config import DEMO_MODE


class DummyLogger:
    """ Replace a `logging.Logger` object with a dummy to save precious time """
    def info(self, *args: Any, **kwargs: Any) -> None:
        ...

demo_logger = logging.getLogger("dank_mids.demo") if DEMO_MODE else DummyLogger()
