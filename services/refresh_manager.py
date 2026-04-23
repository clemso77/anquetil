"""
Refresh Manager Module

Manages automatic data refresh with a configurable interval and a manual
refresh trigger.  Uses a single long-lived daemon thread (not a chain of
``threading.Timer`` objects) so that the manager is safe to stop/join at any
time without race conditions or timer-chain drift.
"""

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RefreshManager:
    """
    Manages periodic data refresh with auto-refresh and manual trigger.

    A single background daemon thread sleeps for ``refresh_interval_seconds``
    between cycles.  ``refresh_now()`` wakes the thread early via an internal
    event so the next fetch starts immediately, without spawning an extra thread.
    """

    def __init__(self, refresh_interval_seconds: int = 80):
        """
        Initialise the refresh manager.

        Args:
            refresh_interval_seconds: Seconds between automatic refreshes.
        """
        self.refresh_interval_seconds = refresh_interval_seconds
        self._refresh_callback: Optional[Callable[[], None]] = None
        self._is_refreshing = False
        self._is_running = False
        self._lock = threading.Lock()
        # Woken when the thread should run a refresh early (manual trigger).
        self._wakeup_event = threading.Event()
        # Set when stop() is called so the thread exits cleanly.
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_refresh_callback(self, callback: Callable[[], None]):
        """
        Set the callback to invoke on each refresh cycle.

        Args:
            callback: Zero-argument callable executed on each refresh.
        """
        self._refresh_callback = callback

    def start(self, immediate_refresh: bool = True):
        """
        Start the auto-refresh background thread.

        Args:
            immediate_refresh: If ``True``, run a refresh immediately before
                               the first timed interval.
        """
        if self._is_running:
            logger.warning("Refresh manager already running — start() ignored")
            return

        logger.info("Starting refresh manager (interval: %ss)", self.refresh_interval_seconds)
        self._is_running = True
        self._stop_event.clear()
        self._wakeup_event.clear()

        self._worker = threading.Thread(
            target=self._run,
            args=(immediate_refresh,),
            name="RefreshManagerWorker",
            daemon=True,
        )
        self._worker.start()

    def stop(self):
        """Stop the background thread and block until it exits."""
        logger.info("Stopping refresh manager...")
        self._is_running = False
        self._stop_event.set()
        self._wakeup_event.set()  # Unblock any sleeping wait

        if self._worker is not None:
            self._worker.join(timeout=5)
            self._worker = None

        logger.info("Refresh manager stopped")

    def refresh_now(self):
        """
        Trigger an immediate manual refresh without waiting for the next interval.

        The background thread is woken up; no extra thread is spawned.
        """
        logger.info("Manual refresh triggered")
        self._wakeup_event.set()

    def is_refreshing(self) -> bool:
        """Return ``True`` if a refresh callback is currently executing."""
        with self._lock:
            return self._is_refreshing

    def is_running(self) -> bool:
        """Return ``True`` if the background thread is active."""
        return self._is_running

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_refresh(self):
        """Run the refresh callback, guarded against concurrent execution."""
        with self._lock:
            if self._is_refreshing:
                logger.debug("Refresh already in progress, skipping")
                return
            self._is_refreshing = True

        try:
            if self._refresh_callback:
                self._refresh_callback()
        except Exception:
            logger.exception("Unhandled exception during refresh callback")
        finally:
            with self._lock:
                self._is_refreshing = False

    def _run(self, immediate_refresh: bool):
        """Background worker loop."""
        if immediate_refresh:
            self._execute_refresh()

        while not self._stop_event.is_set():
            # Sleep for the configured interval — or until woken early.
            woken_early = self._wakeup_event.wait(timeout=self.refresh_interval_seconds)
            if self._stop_event.is_set():
                break
            if woken_early:
                self._wakeup_event.clear()
            self._execute_refresh()


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_refresh_manager_instance: Optional[RefreshManager] = None


def get_refresh_manager(refresh_interval_seconds: int = 80) -> RefreshManager:
    """
    Return the singleton :class:`RefreshManager` instance.

    Args:
        refresh_interval_seconds: Used only on first creation.
    """
    global _refresh_manager_instance
    if _refresh_manager_instance is None:
        _refresh_manager_instance = RefreshManager(refresh_interval_seconds)
    return _refresh_manager_instance
