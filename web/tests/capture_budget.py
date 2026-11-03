"""Pure byte-budget arithmetic; does not approve files or alter an inventory."""
from __future__ import annotations

VIDEO_PATH = 'media/afterlight-desktop-demo.mp4'
LIMIT_BYTES = 50_000_000


def _byte_count(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(label + ' must be a nonnegative integer byte count')
    return value


def project_release_budget(manifest: dict, new_video_bytes: int) -> dict:
    """Replace only the canonical video's bytes, retaining every other file.

    A first video adds its bytes. An existing video is subtracted once before
    its replacement is added. The declared total must match every file entry;
    booleans, floats and negative byte counts are never accepted as integers.
    """
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict):
        raise ValueError('Manifest must contain a file inventory object')
    new_bytes = _byte_count(new_video_bytes, 'New video')
    current_bytes = _byte_count(manifest.get('total_bytes'), 'Manifest total')
    inventory = manifest['files']
    counted_bytes = 0
    for name, item in inventory.items():
        if not isinstance(name, str) or not name or not isinstance(item, dict):
            raise ValueError('Manifest file entries must have names and byte metadata')
        counted_bytes += _byte_count(item.get('bytes'), 'File ' + name)
    if counted_bytes != current_bytes:
        raise ValueError('Manifest total does not equal its complete file inventory')
    existing_bytes = inventory[VIDEO_PATH]['bytes'] if VIDEO_PATH in inventory else 0
    projected = current_bytes - existing_bytes + new_bytes
    return {'video_path': VIDEO_PATH, 'current_total_bytes': current_bytes,
            'replaces_existing_video': VIDEO_PATH in inventory,
            'existing_video_bytes': existing_bytes, 'new_video_bytes': new_bytes,
            'projected_total_bytes': projected, 'limit_bytes': LIMIT_BYTES,
            'within_limit': projected < LIMIT_BYTES}
