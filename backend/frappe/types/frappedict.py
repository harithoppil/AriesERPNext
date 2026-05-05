"""
Frappe's dict subclass that allows attribute-style access.
This is a core type used throughout the framework.
"""


class _dict(dict):
    """Dictionary subclass that allows attribute-style access.

    All document dictionaries in Frappe are _dict instances, so you can do:
        doc.name  # attribute access
        doc["name"]  # dict access
    """

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")

    def __getstate__(self):
        return self.__dict__

    def __setstate__(self, state):
        self.__dict__.update(state)

    def copy(self):
        return _dict(super().copy())

    def update(self, *args, **kwargs):
        return super().update(*args, **kwargs)

    def get(self, key, default=None):
        return super().get(key, default)

    def setdefault(self, key, default=None):
        return super().setdefault(key, default)
