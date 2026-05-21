import threading
import time
from redis_coordinator import RedisCoordinator
from enums import AgentStatus
from hook_registry import hooks

class AgentBase:
    def __init__(self, agent_id, channel='tasks', redis_host='localhost', redis_port=6379, redis_db=0):
        self.agent_id = agent_id
        self.status = AgentStatus.WAITING_FOR_INPUT
        self.coordinator = RedisCoordinator(agent_id, channel, redis_host, redis_port, redis_db)
        self.heartbeat_interval = 5
        self._stop_event = threading.Event()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)

    def start(self):
        hooks.trigger('pre_agent_start', self)
        self._heartbeat_thread.start()
        hooks.trigger('post_agent_start', self)

    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            hooks.trigger('pre_heartbeat', self)
            self.send_heartbeat()
            hooks.trigger('post_heartbeat', self)
            self._stop_event.wait(self.heartbeat_interval)

    def send_heartbeat(self):
        hooks.trigger('pre_communication', self, event_key='heartbeat')
        self.coordinator.publish('HEARTBEAT', 'heartbeat', {'status': self.status.value})
        hooks.trigger('post_communication', self, event_key='heartbeat')

    def update_status(self, status):
        hooks.trigger('pre_status_update', self, new_status=status)
        self.status = status
        self.coordinator.publish('STATUS', 'status_update', {'status': self.status.value})
        hooks.trigger('post_status_update', self, new_status=status)

    def stop(self):
        hooks.trigger('pre_agent_stop', self)
        self._stop_event.set()
        self._heartbeat_thread.join(timeout=1)
        hooks.trigger('post_agent_stop', self)
