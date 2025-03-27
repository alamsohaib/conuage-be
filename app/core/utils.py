import json
from uuid import UUID

class UUIDEncoder(json.JSONEncoder):
    """Custom JSON encoder for UUID objects"""
    def default(self, obj):
        if isinstance(obj, UUID):
            # if the obj is uuid, we simply return the value of uuid
            return str(obj)
        return json.JSONEncoder.default(self, obj)
