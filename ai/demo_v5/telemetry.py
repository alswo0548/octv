"""Best-effort exact-frame preview, isolated from inference/incident decisions."""
import base64
import json
import logging
import os
from datetime import timezone

log = logging.getLogger(__name__)


def client():
    import redis
    return redis.Redis.from_url(os.environ['OCTV_REDIS_URL'], decode_responses=True,
                                socket_timeout=0.3, socket_connect_timeout=0.3)


def publish(frame, detections):
    try:
        import cv2
        ok, encoded = cv2.imencode('.jpg', frame.image, [cv2.IMWRITE_JPEG_QUALITY, 65])
        if not ok:
            return
        height, width = frame.image.shape[:2]
        payload = {'captured_at': frame.captured_at.astimezone(timezone.utc).isoformat(),
                   'width': width, 'height': height,
                   'image': base64.b64encode(encoded.tobytes()).decode(),
                   'detections': [{'hazard_type': d.hazard_type, 'confidence': d.confidence,
                                   'bbox': list(d.bbox), 'model_version': d.model_version} for d in detections]}
        client().setex(f'octv:v5:preview:{frame.cctv_id}', 30, json.dumps(payload))
    except Exception:
        # Preview failure must never discard real detections or stop the runtime.
        log.debug('v5 preview unavailable', exc_info=False)


def observing_detector(detect):
    from .live_metadata import enabled, MetadataPublisher
    publisher = MetadataPublisher() if enabled() else None
    def wrapped(frame):
        detections = detect(frame)
        if publisher is not None:
            publisher.submit(frame, detections)
        else:
            publish(frame, detections)
        return detections
    return wrapped

