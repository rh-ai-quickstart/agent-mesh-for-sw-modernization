import logging
import threading
from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger(__name__)


class BasicTokenLogger(CustomLogger):
    """Accumulates a running token tally. Subclasses override log_tokens() to persist it."""

    def __init__(self):
        self.run_id = None
        self.step = 0
        self.totals = {}
        self._lock = threading.Lock()

    def log_tokens(self) -> None:
        pass

    def _update(self, response_obj):
        usage = getattr(response_obj, "usage", None)
        if not usage:
            return
        with self._lock:
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                val = getattr(usage, key, None)
                if val is not None:
                    self.totals[key] = self.totals.get(key, 0) + int(val)
            self.step += 1
            try:
                self.log_tokens()
            except Exception as exc:
                logger.debug("BasicTokenLogger: %s", exc)

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._update(response_obj)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._update(response_obj)
