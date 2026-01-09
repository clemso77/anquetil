"""
Data Manager Module

Centralizes data state management with proper state tracking.
Manages loading, success, error, and idle states.
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
import threading


class DataState(Enum):
    """Enumeration of possible data states."""
    IDLE = "idle"
    LOADING = "loading"
    SUCCESS = "success"
    ERROR = "error"


class DataManager:
    """
    Manages application data state and provides callbacks for state changes.
    Thread-safe for concurrent access.
    """

    def __init__(self):
        """Initialize the data manager."""
        self._state = DataState.IDLE
        self._data: List[Dict[str, Any]] = []
        self._error_message: Optional[str] = None
        self._last_update: Optional[datetime] = None
        self._lock = threading.Lock()
        self._state_change_callbacks: List[Callable[[DataState], None]] = []

    @property
    def state(self) -> DataState:
        """Get current state (thread-safe)."""
        with self._lock:
            return self._state

    @property
    def data(self) -> List[Dict[str, Any]]:
        """Get current data (thread-safe)."""
        with self._lock:
            return self._data.copy()

    @property
    def error_message(self) -> Optional[str]:
        """Get error message if state is ERROR (thread-safe)."""
        with self._lock:
            return self._error_message

    @property
    def last_update(self) -> Optional[datetime]:
        """Get timestamp of last successful update (thread-safe)."""
        with self._lock:
            return self._last_update

    def add_state_change_callback(self, callback: Callable[[DataState], None]):
        """
        Add a callback to be notified on state changes.
        
        Args:
            callback: Function to call when state changes
        """
        with self._lock:
            self._state_change_callbacks.append(callback)

    def set_loading(self):
        """Set state to LOADING."""
        with self._lock:
            self._state = DataState.LOADING
            self._error_message = None
            callbacks = self._state_change_callbacks.copy()
        
        # Call callbacks outside lock to avoid deadlock
        for callback in callbacks:
            try:
                callback(DataState.LOADING)
            except Exception as e:
                print(f"Error in state change callback: {e}")

    def set_success(self, data: List[Dict[str, Any]]):
        """
        Set state to SUCCESS with new data.
        
        Args:
            data: New data to store
        """
        with self._lock:
            self._state = DataState.SUCCESS
            self._data = data
            self._error_message = None
            self._last_update = datetime.now()
            callbacks = self._state_change_callbacks.copy()
        
        # Call callbacks outside lock
        for callback in callbacks:
            try:
                callback(DataState.SUCCESS)
            except Exception as e:
                print(f"Error in state change callback: {e}")

    def set_error(self, error_message: str):
        """
        Set state to ERROR with error message.
        
        Args:
            error_message: Description of the error
        """
        with self._lock:
            self._state = DataState.ERROR
            self._error_message = error_message
            # Keep old data if available
            callbacks = self._state_change_callbacks.copy()
        
        # Call callbacks outside lock
        for callback in callbacks:
            try:
                callback(DataState.ERROR)
            except Exception as e:
                print(f"Error in state change callback: {e}")

    def has_data(self) -> bool:
        """
        Check if there is any data available.
        
        Returns:
            bool: True if data exists
        """
        with self._lock:
            return len(self._data) > 0

    def get_formatted_items(self, limit: int = 2) -> List[Dict[str, Any]]:
        """
        Get formatted data items ready for display.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of formatted dictionaries with:
                - wait_minutes: Minutes until departure
                - destination: Destination name
                - line: Line identifier
                - status: Departure status (e.g., 'onTime', 'delayed', 'NO_REPORT')
        """
        with self._lock:
            items = []
            for item in self._data[:limit]:
                items.append({
                    "wait_minutes": int(item.get("wait_minutes", 0)),
                    "destination": item.get("destination") or item.get("destination_ref") or "",
                    "line": item.get("line") or item.get("line_ref") or "",
                    "status": item.get("status") or "",
                })
            return items


# Singleton instance
_data_manager_instance: Optional[DataManager] = None


def get_data_manager() -> DataManager:
    """
    Get the singleton data manager instance.
    
    Returns:
        DataManager: The data manager instance
    """
    global _data_manager_instance
    if _data_manager_instance is None:
        _data_manager_instance = DataManager()
    return _data_manager_instance
