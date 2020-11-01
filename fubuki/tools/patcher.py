class Patcher:
    """
    Utility class to facilitate monkeypatching... stuff

    Initialise class with a target, which can be a module, or a class
        or maybe other things I don't know
    """

    def __init__(self, target):
        self.target = target
        self._to_set = {}
        self._backup = {}
        for name, attr in map(
                lambda i: (i, getattr(target, i)),
                dir(target)):
            self._backup[name] = attr

    def attribute(self, value=None, *, name=None):
        """
        Patch an attribute onto the target.

        This method can be used as a normal function or as a decorator.

        If `value` is given, then that value will be patched, under
        the name parameter, or its __name__ value

        This can also be used to decorate a function or a class.
        It can be used to add methods to classes, classes to modules, etc.

        Note that by itself, this method only stores the new attribute
        internally. The patch() method applies the patch itself.
        """
        if value is not None:
            self._to_set[getattr(value, '__name__', name)] = value
            return

        def inner(attr):
            self._to_set[getattr(attr, '__name__', name)] = attr
        return inner

    def patch(self):
        """
        Applies all staged patches to the target.
        """
        for name, attr in self._to_set.items():
            setattr(self.target, name, attr)

    def revert(self):
        """
        Reverts the target back to its state at the time that the
        Patcher was instantiated.

        Any *new* attributes will be removed, and all overridden
        attributes will be reverted.
        """
        for name in self._to_set.keys():
            delattr(self.target, name)
        for name, attr in self._backup.items():
            setattr(self.target, name, attr)