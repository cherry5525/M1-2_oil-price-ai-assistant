"""간단한 요청 횟수 제한. 서버 전체 요청을 합산하며 메모리에만 기록한다.

한계: 서버가 재시작되면 기록이 초기화되고, 사용자별 구분은 하지 않는다. (README '알려진 한계' 참고)
"""
import math
import time
from collections import deque
from threading import Lock
from typing import Callable, Tuple

from config import CHAT_DAILY_LIMIT, CHAT_RATE_LIMIT_PER_MINUTE

MINUTE_SECONDS = 60
DAY_SECONDS = 24 * 60 * 60


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int, clock: Callable[[], float] = time.monotonic):
        self.per_minute = per_minute
        self.per_day = per_day
        self._clock = clock
        self._minute = deque()  # 최근 1분 동안의 요청 시각
        self._day = deque()     # 최근 24시간 동안의 요청 시각
        self._lock = Lock()

    def acquire(self) -> Tuple[bool, int, str]:
        """요청 1건을 허용할 수 있으면 기록하고 (True, 0, "")을 반환한다.
        한도를 넘으면 기록하지 않고 (False, 다시 시도할 때까지 남은 초, "minute" 또는 "day")를 반환한다."""
        now = self._clock()
        with self._lock:
            while self._minute and now - self._minute[0] >= MINUTE_SECONDS:
                self._minute.popleft()
            while self._day and now - self._day[0] >= DAY_SECONDS:
                self._day.popleft()

            if len(self._minute) >= self.per_minute:
                return False, max(1, math.ceil(MINUTE_SECONDS - (now - self._minute[0]))), "minute"
            if len(self._day) >= self.per_day:
                return False, max(1, math.ceil(DAY_SECONDS - (now - self._day[0]))), "day"

            self._minute.append(now)
            self._day.append(now)
            return True, 0, ""


chat_limiter = RateLimiter(CHAT_RATE_LIMIT_PER_MINUTE, CHAT_DAILY_LIMIT)
