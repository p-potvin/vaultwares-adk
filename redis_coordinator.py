try:
    import redis
except ImportError:
    redis = None
import threading
import json
import logging

logger = logging.getLogger(__name__)

class RedisCoordinator:
    def __init__(self, agent_id, channel='tasks', host='localhost', port=6379, db=0):
        if redis is None:
            raise RuntimeError("redis package is required: pip install redis")
        self.agent_id = agent_id
        self.channel = channel
        self.r = redis.Redis(host=host, port=port, db=db)
        self.pubsub = self.r.pubsub()
        self.pubsub.subscribe(channel)
        self.listener_thread = None
        self.running = False

    def publish(self, action, task, details=None):
        msg = {
            'agent': self.agent_id,
            'action': action,
            'task': task,
            'details': details or {}
        }
        self.r.publish(self.channel, json.dumps(msg))

    def set_state(self, key, value, ex=None):
        self.r.set(key, value, ex=ex)

    def get_state(self, key):
        return self.r.get(key)

    def listen(self, callback):
        def _listen():
            for message in self.pubsub.listen():
                if not self.running:
                    break
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        callback(data)
                    except (json.JSONDecodeError, TypeError) as exc:
                        logger.warning("Skipping malformed Redis message: %s", exc)
        self.running = True
        self.listener_thread = threading.Thread(target=_listen, daemon=True)
        self.listener_thread.start()

    def stop(self):
        self.running = False
        if self.listener_thread:
            self.listener_thread.join(timeout=1)
