import threading
import time

class BusDataService:
    INTERVAL_SECONDS = 80

    def __init__(self, fetch_fn, stop_point_ref):
        self.fetch_fn = fetch_fn
        self.stop_point_ref = stop_point_ref
        self.data = []
        self.error = None
        self.loading = False
        self._interval = None
        self._lock = threading.Lock()
        self._abort_event = threading.Event()

    def start(self, update_callback):
        """Démarre le refresh automatique; appelle update_callback(data, loading, error) à chaque changement."""
        self._abort_event.clear()
        self._run_poll(update_callback)

    def stop(self):
        self._abort_event.set()
        if self._interval:
            self._interval.cancel()

    def force_refresh(self, update_callback):
        """Refresh immédiat (bouton), pas de doublon."""
        if self.loading:
            return # ou bien cancel et refetch si tu veux plus smart
        self._fetch(update_callback)

    def _run_poll(self, update_callback):
        def poll():
            if self._abort_event.is_set():
                return
            self._fetch(update_callback)
            # Planifie le prochain appel
            self._interval = threading.Timer(self.INTERVAL_SECONDS, self._run_poll, args=(update_callback,))
            self._interval.start()
        poll()

    def _fetch(self, update_callback):
        with self._lock:
            self.loading = True
            update_callback(self.data, True, None)
            try:
                data = self.fetch_fn(self.stop_point_ref, 2)
                self.data = data
                self.error = None
            except Exception as e:
                self.error = e
            self.loading = False
            update_callback(self.data, False, self.error)