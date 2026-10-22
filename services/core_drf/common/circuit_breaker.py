import time
import logging
import threading
from enum import Enum
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"       # Normal operation, requests pass through
    OPEN = "OPEN"           # Failing, requests fast-fail without calling backend
    HALF_OPEN = "HALF_OPEN" # Testing recovery with a canary request

class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    pass

class CircuitBreaker:
    """
    Production-grade Circuit Breaker pattern for distributed caches and external services.
    
    Protects downstream infrastructure (Redis, microservices) from cascading failures.
    If Redis throws consecutive connection errors exceeding failure_threshold, the circuit
    trips OPEN for recovery_timeout seconds, immediately diverting traffic to graceful fallbacks.
    """
    def __init__(
        self,
        name: str = "redis_service",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exceptions: tuple = (Exception,)
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Executes func wrapped in circuit breaker safety checks."""
        with self._lock:
            now = time.time()
            if self.state == CircuitState.OPEN:
                if now - self.last_failure_time > self.recovery_timeout:
                    logger.info("CircuitBreaker [%s]: Recovery timeout elapsed. Transitioning OPEN -> HALF_OPEN", self.name)
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerOpenException(
                        f"CircuitBreaker [{self.name}] is OPEN. Fast-failing request."
                    )

        # Attempt the call
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exceptions as exc:
            self._on_failure(exc)
            raise

    def _on_success(self):
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                logger.info("CircuitBreaker [%s]: Canary call succeeded. Resetting HALF_OPEN -> CLOSED", self.name)
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    def _on_failure(self, exc: Exception):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            logger.warning(
                "CircuitBreaker [%s]: Call failed (%d/%d): %s",
                self.name, self.failure_count, self.failure_threshold, str(exc)
            )
            if self.failure_count >= self.failure_threshold or self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.error(
                    "CircuitBreaker [%s]: Failure threshold reached! Tripping circuit to OPEN for %ds.",
                    self.name, self.recovery_timeout
                )

# Global Circuit Breakers for Infrastructure Dependencies
redis_circuit_breaker = CircuitBreaker(
    name="redis_cache",
    failure_threshold=5,
    recovery_timeout=25.0
)
