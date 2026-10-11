"""요청 횟수 제한기(services/rate_limiter.py) 테스트. 시계를 직접 조작해서 시간이 흐르는 상황을 흉내 낸다."""
from services.rate_limiter import RateLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_per_minute_limit_blocks_and_recovers():
    clock = Clock()
    limiter = RateLimiter(per_minute=3, per_day=100, clock=clock)
    assert all(limiter.acquire()[0] for _ in range(3))

    allowed, retry_after, reason = limiter.acquire()
    assert (allowed, reason) == (False, "minute")
    assert 1 <= retry_after <= 60

    clock.now += 61  # 1분이 지나면 다시 허용
    assert limiter.acquire()[0] is True


def test_retry_after_counts_down():
    clock = Clock()
    limiter = RateLimiter(per_minute=1, per_day=100, clock=clock)
    limiter.acquire()
    clock.now += 40
    assert limiter.acquire() == (False, 20, "minute")


def test_per_day_limit():
    clock = Clock()
    limiter = RateLimiter(per_minute=1000, per_day=5, clock=clock)
    for _ in range(5):
        assert limiter.acquire()[0]
        clock.now += 30  # 분당 한도에는 걸리지 않게 간격을 둔다
    allowed, retry_after, reason = limiter.acquire()
    assert (allowed, reason) == (False, "day")
    assert retry_after > 3600

    clock.now += 24 * 3600  # 하루가 지나면 다시 허용
    assert limiter.acquire()[0] is True


def test_rejected_requests_are_not_recorded():
    clock = Clock()
    limiter = RateLimiter(per_minute=1, per_day=100, clock=clock)
    limiter.acquire()
    for _ in range(10):
        assert limiter.acquire()[0] is False  # 거절된 요청이 기록되어 한도 해제를 늦추면 안 됨
    clock.now += 61
    assert limiter.acquire()[0] is True
