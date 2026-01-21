"""
String methods.
"""

import uuid


class Uuid:
    @staticmethod
    def is_valid_uuid_v4(uuid_string):
        """
        Checks if a string is a valid Version 4 UUID.
        """
        try:
            uuid_obj = uuid.UUID(uuid_string)
            return uuid_obj.version == 4
        except ValueError:
            return False
