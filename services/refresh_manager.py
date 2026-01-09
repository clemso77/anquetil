"""
Refresh Manager Module

Manages automatic data refresh with configurable interval and manual refresh capability.
Handles timer lifecycle and prevents duplicate requests.
"""

import threading
import time
from typing import Callable, Optional


class RefreshManager:
    """
    Manages periodic data refresh with auto-refresh timer and manual trigger.
    Ensures proper cleanup and prevents duplicate requests.
    """

    def __init__(self, refresh_interval_seconds: int = 80):
        """
        Initialize the refresh manager.
        
        Args:
            refresh_interval_seconds: Interval between automatic refreshes (default: 80)
        """
        self.refresh_interval_seconds = refresh_interval_seconds
        self._timer: Optional[threading.Timer] = None
        self._is_running = False
        self._refresh_callback: Optional[Callable[[], None]] = None
        self._is_refreshing = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def set_refresh_callback(self, callback: Callable[[], None]):
        """
        Set the callback to execute on each refresh.
        
        Args:
            callback: Function to call when refresh is triggered
        """
        self._refresh_callback = callback

    def _execute_refresh(self):
        """Execute the refresh callback if not already refreshing."""
        with self._lock:
            if self._is_refreshing:
                print("Refresh already in progress, skipping...")
                return
            self._is_refreshing = True

        try:
            if self._refresh_callback:
                self._refresh_callback()
        except Exception as e:
            print(f"Error during refresh: {e}")
        finally:
            with self._lock:
                self._is_refreshing = False

    def _schedule_next_refresh(self):
        """Schedule the next automatic refresh."""
        if not self._is_running:
            return

        def refresh_task():
            if self._is_running:
                self._execute_refresh()
                self._schedule_next_refresh()

        self._timer = threading.Timer(self.refresh_interval_seconds, refresh_task)
        self._timer.daemon = True
        self._timer.start()

    def start(self, immediate_refresh: bool = True):
        """
        Start the auto-refresh timer.
        
        Args:
            immediate_refresh: If True, triggers an immediate refresh before starting timer
        """
        if self._is_running:
            print("Refresh manager already running")
            return

        print(f"Starting refresh manager (interval: {self.refresh_interval_seconds}s)")
        self._is_running = True
        self._stop_event.clear()

        # Immediate refresh if requested
        if immediate_refresh:
            self._execute_refresh()

        # Schedule periodic refreshes
        self._schedule_next_refresh()

    def stop(self):
        """Stop the auto-refresh timer and cleanup."""
        print("Stopping refresh manager...")
        self._is_running = False
        self._stop_event.set()

        # Cancel pending timer
        if self._timer:
            self._timer.cancel()
            self._timer = None

        print("Refresh manager stopped")

    def refresh_now(self):
        """
        Trigger an immediate manual refresh.
        This does not reset the auto-refresh interval.
        """
        print("Manual refresh triggered")
        
        # Execute refresh in a separate thread to avoid blocking
        refresh_thread = threading.Thread(target=self._execute_refresh)
        refresh_thread.daemon = True
        refresh_thread.start()

    def is_refreshing(self) -> bool:
        """
        Check if a refresh is currently in progress.
        
        Returns:
            bool: True if refresh is in progress
        """
        with self._lock:
            return self._is_refreshing

    def is_running(self) -> bool:
        """
        Check if the refresh manager is active.
        
        Returns:
            bool: True if refresh manager is running
        """
        return self._is_running


# Singleton instance
_refresh_manager_instance: Optional[RefreshManager] = None


def get_refresh_manager(refresh_interval_seconds: int = 80) -> RefreshManager:
    """
    Get the singleton refresh manager instance.
    
    Args:
        refresh_interval_seconds: Refresh interval (only used on first call)
        
    Returns:
        RefreshManager: The refresh manager instance
    """
    global _refresh_manager_instance
    if _refresh_manager_instance is None:
        _refresh_manager_instance = RefreshManager(refresh_interval_seconds)
    return _refresh_manager_instance
