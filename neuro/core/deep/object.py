class Object(object):
    def __init__(self, labels=None, properties=None):
        # Set labels
        if labels is None:
            self.labels = list()
        elif isinstance(labels, list):
            self.labels = labels
        else:
            raise TypeError(f"Labels must be a list or None, got {type(labels).__name__}")

        # Set properties
        if properties is None:
            self.properties = dict()
        elif isinstance(properties, dict):
            self.properties = properties
        else:
            raise TypeError(f"Properties must be a dict or None, got {type(properties).__name__}")