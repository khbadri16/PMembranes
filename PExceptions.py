# ══════════════════════════════════════════════════════
#  EXCEPTIONS
# ══════════════════════════════════════════════════════

class RootDissolveError(Exception):
    def __init__(self, name: str):
        super().__init__(f"Cannot dissolve membrane '{name}': it is the root membrane.")


class ElementaryMembraneError(Exception):
    """
    Raised when an action returns INTO() or INTO("name") but the membrane has no children.
    Always raised in strict mode (no silent skip), to prevent "mutated but not applied".
    """
    def __init__(self, membrane_name: str, child_name: str = "<random>"):
        super().__init__(
            f"Cannot send object INTO('{child_name}'): membrane '{membrane_name}' "
            f"is elementary (has no children). Add m.has_children() or "
            f"m.has_child('{child_name}') to the guard."
        )


class ActionReturnedNoneError(Exception):
    def __init__(self, rule_name: str, obj_repr: str):
        super().__init__(
            f"Action '{rule_name}' returned None for {obj_repr}. "
            f"Every action must return a Signal (or (Signal, produced_list))."
        )


class MembraneCycleError(Exception):
    def __init__(self, parent_name: str, child_name: str):
        super().__init__(
            f"Cannot nest membrane '{child_name}' inside '{parent_name}': this would "
            f"create a cycle. '{parent_name}' is already a descendant of '{child_name}'."
        )


class InvalidObjectTypeError(Exception):
    def __init__(self, obj):
        super().__init__(
            f"Object {obj!r} (type {type(obj).__name__}) does not inherit from PObject. "
            f"All objects stored in membranes must subclass PObject."
        )


class ObjectAlreadyPlacedError(Exception):
    def __init__(self, obj, current_mem, target_mem):
        super().__init__(
            f"Object {obj!r} is already placed in membrane '{current_mem._name}'. "
            f"Cannot also place it in '{target_mem._name}'. Clone the object if you need "
            f"copies in multiple membranes."
        )
