import copy
import random
import inspect
from typing import get_type_hints
from PException import RootDissolveError, MembraneCycleError, ElementaryMembraneError, \
    ObjectAlreadyPlacedError, InvalidObjectTypeError, ActionReturnedNoneError



# ══════════════════════════════════════════════════════
#  PObject — base class for all membrane objects
# ══════════════════════════════════════════════════════

class PObject:
    """
    Base class for all objects that can live inside a Membrane.
    Tracks current owner membrane via _membrane.
    """
    def __init__(self):
        self._membrane = None


# ══════════════════════════════════════════════════════
#  SIGNALS
# ══════════════════════════════════════════════════════

class _Signal:
    def __init__(self, _diss: bool = False):
        self._diss = _diss

    @property
    def dissolve(self):
        s = copy.copy(self)
        s._diss = True
        return s

class _Stay(_Signal):   pass
class _Vanish(_Signal): pass
class _Out(_Signal):    pass

class _Into(_Signal):
    def __init__(self, child_name: str = None, _diss: bool = False):
        super().__init__(_diss)
        self.child_name = child_name

    @property
    def dissolve(self):
        return _Into(self.child_name, _diss=True)

class _Clone(_Signal):
    def __init__(self, n: int = 1, fn=None, _diss: bool = False):
        super().__init__(_diss)
        self._n  = n
        self._fn = fn

    def with_fn(self, fn) -> "_Clone":
        return _Clone(self._n, fn, self._diss)

    def times(self, n: int) -> "_Clone":
        return _Clone(n, self._fn, self._diss)

    @property
    def dissolve(self):
        return _Clone(self._n, self._fn, _diss=True)

def INTO(child_name: str = None) -> _Into: return _Into(child_name)

OUT      = _Out()
STAY     = _Stay()
VANISH   = _Vanish()
CLONE    = _Clone()
DISSOLVE = _Vanish(_diss=True)


# ══════════════════════════════════════════════════════
#  RuleSpec — unified descriptor for arity-1 and arity-N rules
# ══════════════════════════════════════════════════════

class RuleSpec:
    """
    arity : number of object parameters (1 for normal rule, N for multi-object rule)
    types : list[type], length=arity, type filters for each parameter (default PObject)
    guard : callable(*objs) -> bool   (pure)
    action: bound method callable(*objs) -> result
    """
    __slots__ = ("arity", "types", "guard", "action", "name")

    def __init__(self, arity: int, types: list, guard, action, name: str):
        self.arity  = arity
        self.types  = types
        self.guard  = guard
        self.action = action
        self.name   = name

    def __repr__(self):
        return f"RuleSpec(name={self.name!r}, arity={self.arity}, types={[t.__name__ for t in self.types]})"


# ══════════════════════════════════════════════════════
#  GLOBAL @when(guard) DECORATOR  — for class-level rules
# ══════════════════════════════════════════════════════

def when(guard_fn):
    """
    Decorator for Membrane subclass methods.

    Single-object rule:
        @when(lambda obj: ...)
        def r(self, obj: Token): ...

    Multi-object rule:
        @when(lambda a,b,c: ...)
        def r(self, a: A, b: B, c: C): ...
    """
    def decorator(method):
        method._p_guard = guard_fn
        return method
    return decorator


# ══════════════════════════════════════════════════════
#  MEMBRANE
# ══════════════════════════════════════════════════════

class Membrane:
    def __init__(self, name: str):
        self._name             = name
        self._objects          : list  = []
        self._children         : list  = []
        self._parent                   = None

        # Rule list in source order; RuleSpec supports arity=1 and arity>1
        self._rules            : list[RuleSpec] = []

        self._last_fired       : bool  = True
        self._pending_dissolve : bool  = False

        # buffering for movement semantics
        self._inbox            : list  = []
        self._next_inbox       : list  = []

        # ── register class-level rules (direct subclass only) ──
        # No inheritance, no MRO scanning.
        # Uses method signature for arity and type hints for dispatch.
        for attr_name, method in type(self).__dict__.items():
            if not callable(method) or not hasattr(method, "_p_guard"):
                continue

            sig = inspect.signature(method)
            params = list(sig.parameters.keys())
            obj_params = params[1:]   # skip self
            arity = len(obj_params)
            if arity <= 0:
                continue

            try:
                hints = get_type_hints(method, globalns=method.__globals__, localns=vars(type(self)))
            except Exception:
                hints = {}

            types = []
            for p in obj_params:
                t = hints.get(p, PObject)
                # typing.Any / Union / etc can break isinstance; fall back to PObject
                if not isinstance(t, type):
                    t = PObject
                types.append(t)

            bound_action = method.__get__(self, type(self))
            self._rules.append(RuleSpec(
                arity=arity,
                types=types,
                guard=method._p_guard,
                action=bound_action,
                name=attr_name
            ))

    # ── DSL: add object ──────────────────────────────
    def __iadd__(self, obj: PObject):
        if not isinstance(obj, PObject):
            raise InvalidObjectTypeError(obj)
        if obj._membrane is not None and obj._membrane is not self:
            raise ObjectAlreadyPlacedError(obj, obj._membrane, self)
        if obj._membrane is self and obj in self._objects:
            raise ValueError(
                f"Object {obj!r} is already present in membrane '{self._name}'. "
                f"An object cannot appear twice in the same membrane."
            )
        obj._membrane = self
        self._objects.append(obj)
        return self

    # ── DSL: add child ───────────────────────────────
    def __lshift__(self, child: "Membrane"):
        if child is self:
            raise MembraneCycleError(self._name, self._name)
        if self._is_ancestor(child):
            raise MembraneCycleError(self._name, child._name)
        if child._parent is not None:
            raise ValueError(
                f"Membrane '{child._name}' already has parent '{child._parent._name}'. "
                f"Detach it first before re-parenting."
            )
        child._parent = self
        self._children.append(child)
        return self

    def _is_ancestor(self, other: "Membrane") -> bool:
        cursor = self._parent
        while cursor is not None:
            if cursor is other:
                return True
            cursor = cursor._parent
        return False

    # ── instance DSL helpers used in rule bodies ──────
    def stay(self)   -> _Stay:   return STAY
    def vanish(self) -> _Vanish: return VANISH
    def out(self)    -> _Out:    return OUT
    def clone(self)  -> _Clone:  return CLONE

    def into(self, child=None) -> _Into:
        if child is None:
            return INTO()
        if isinstance(child, Membrane):
            if child not in self._children:
                raise ValueError(
                    f"Membrane '{child._name}' is not a direct child of '{self._name}'. "
                    f"Add it first with self << child."
                )
            return INTO(child._name)
        return INTO(child)  # string name

    # ── guard helpers ─────────────────────────────────
    def has_children(self) -> bool: return bool(self._children)
    def has_child(self, name: str) -> bool:
        return any(c._name == name for c in self._children)

    def child(self, name: str) -> "Membrane":
        for c in self._children:
            if c._name == name:
                return c
        raise KeyError(f"No child named '{name}'")

    # ══════════════════════════════════════════════════
    #  TWO-INBOX STEP INFRASTRUCTURE
    # ══════════════════════════════════════════════════

    def _flush_inbox(self):
        if self._inbox:
            for obj in self._inbox:
                obj._membrane = self
            self._objects.extend(self._inbox)
            self._inbox.clear()
        for child in self._children:
            child._flush_inbox()

    def _commit_deliveries(self):
        if self._next_inbox:
            self._inbox.extend(self._next_inbox)
            self._next_inbox.clear()
        for child in self._children:
            child._commit_deliveries()

    # ══════════════════════════════════════════════════
    #  EXECUTION
    # ══════════════════════════════════════════════════

    def step(self) -> bool:
        fired = self._apply_rules()
        for child in list(self._children):
            fired |= child.step()
        self._last_fired = fired
        if self._pending_dissolve:
            self._pending_dissolve = False
            self._dissolve()
        return fired

    # ──────────────────────────────────────────────────
    #  ACTION RETURN PARSING
    # ──────────────────────────────────────────────────

    def _parse_result(self, result, arity: int, rule: RuleSpec, objs: list):
        """
        Return (signals_list, produced_list).

        Arity-1:
            Signal                    -> ([Signal], [])
            (Signal, [new,...])       -> ([Signal], [new,...])

        Arity-N:
            [S1,...,SN]               -> ([S1,...,SN], [])
            (signals_iter, [new,...]) -> ([S1,...,SN], [new,...])
        """
        if result is None:
            raise ActionReturnedNoneError(rule.name, repr(objs))

        # wrapper form: (signals_part, produced_list)
        if (
            isinstance(result, tuple) and len(result) == 2
            and isinstance(result[1], list)
        ):
            signals_part, produced = result
        else:
            signals_part, produced = result, []

        if arity == 1:
            if not isinstance(signals_part, _Signal):
                raise ValueError(
                    f"Rule '{rule.name}' (arity=1) must return a Signal or (Signal, produced_list). "
                    f"Got: {signals_part!r}"
                )
            signals = [signals_part]
        else:
            try:
                signals = list(signals_part)
            except TypeError as e:
                raise ValueError(
                    f"Rule '{rule.name}' (arity={arity}) must return an iterable of {arity} Signals "
                    f"or (signals_iterable, produced_list). Got: {signals_part!r}"
                ) from e
            if len(signals) != arity:
                raise ValueError(
                    f"Rule '{rule.name}' (arity={arity}) returned {len(signals)} signals; "
                    f"expected exactly {arity}."
                )

        # Validate signals are Signal objects
        for s in signals:
            if not isinstance(s, _Signal):
                raise ValueError(
                    f"Rule '{rule.name}' returned non-Signal element in signals: {s!r}"
                )

        return signals, produced

    def _validate_produced(self, produced: list):
        """
        Produced objects must be fresh PObject instances (not already owned by a membrane).
        Ownership is set immediately to this membrane.
        """
        for obj in produced:
            if not isinstance(obj, PObject):
                raise InvalidObjectTypeError(obj)
            if obj._membrane is not None:
                raise ObjectAlreadyPlacedError(obj, obj._membrane, self)
            obj._membrane = self

    # ──────────────────────────────────────────────────
    #  SIGNAL COMMIT (one object)
    # ──────────────────────────────────────────────────

    def _commit_signal(self, obj: PObject, sig: _Signal, to_add: list):
        """
        Apply one signal to one object. Immediate removal/movement:
        the same instance is never in two containers at once.
        """
        if isinstance(sig, _Stay):
            return

        if isinstance(sig, _Vanish):
            if obj in self._objects:
                self._objects.remove(obj)
            obj._membrane = None
            return

        if isinstance(sig, _Out):
            if obj in self._objects:
                self._objects.remove(obj)
            if self._parent is not None:
                obj._membrane = self._parent
                self._parent._next_inbox.append(obj)
            else:
                obj._membrane = None
            return

        if isinstance(sig, _Into):
            if not self._children:
                raise ElementaryMembraneError(self._name, sig.child_name or "<random>")

            if sig.child_name is None:
                dest = random.choice(self._children)
            else:
                dest = next((c for c in self._children if c._name == sig.child_name), None)
                if dest is None:
                    raise KeyError(f"No child named '{sig.child_name}' in membrane '{self._name}'")

            if obj in self._objects:
                self._objects.remove(obj)
            obj._membrane = dest
            dest._next_inbox.append(obj)
            return

        if isinstance(sig, _Clone):
            # Original stays; clones are queued.
            for _ in range(sig._n):
                new_obj = copy.deepcopy(obj)
                new_obj._membrane = self
                if sig._fn:
                    sig._fn(new_obj)
                to_add.append(new_obj)
            return

        raise ValueError(f"Unknown signal type: {sig!r}")

    # ──────────────────────────────────────────────────
    #  MATCHING HELPERS
    # ──────────────────────────────────────────────────

    def _available(self, obj: PObject, used_ids: set) -> bool:
        """True if obj is still in this membrane and hasn't been used this step."""
        return (obj._membrane is self) and (id(obj) not in used_ids)

    def _match_rule_for_anchor(self, rule: RuleSpec, anchor: PObject, snapshot: list, used_ids: set):
        """
        Try to match `rule` using `anchor` as a required participant.
        Returns list of matched objects in parameter order, or None.

        • For arity=1, it's just [anchor] if it matches.
        • For arity>1, we try placing anchor into ANY slot where its type fits,
          and backtrack to fill remaining slots from available objects.
        """
        if rule.arity == 1:
            if not self._available(anchor, used_ids):
                return None
            if not isinstance(anchor, rule.types[0]):
                return None
            if rule.guard(anchor):
                return [anchor]
            return None

        if not self._available(anchor, used_ids):
            return None

        # try anchor in any slot whose type it matches
        for anchor_slot in range(rule.arity):
            if not isinstance(anchor, rule.types[anchor_slot]):
                continue

            chosen = [None] * rule.arity
            chosen[anchor_slot] = anchor
            chosen_ids = {id(anchor)}

            def fill(slot: int):
                if slot == rule.arity:
                    # all slots filled; test guard
                    if rule.guard(*chosen):
                        return chosen
                    return None

                if chosen[slot] is not None:
                    return fill(slot + 1)

                for cand in snapshot:
                    if cand is None:
                        continue
                    if id(cand) in chosen_ids:
                        continue
                    if not self._available(cand, used_ids):
                        continue
                    if not isinstance(cand, rule.types[slot]):
                        continue

                    chosen[slot] = cand
                    chosen_ids.add(id(cand))
                    res = fill(slot + 1)
                    if res is not None:
                        return res
                    chosen_ids.remove(id(cand))
                    chosen[slot] = None

                return None

            res = fill(0)
            if res is not None:
                return res

        return None

    # ──────────────────────────────────────────────────
    #  MAIN RULE APPLICATION (object-outer, rule-inner)
    # ──────────────────────────────────────────────────

    def _apply_rules(self) -> bool:
        """
        Apply rules in the "original design" style:
          For each object (in a snapshot), try rules in order until one commits.

        Multi-object rules are supported:
          If a multi-rule commits, it consumes/affects multiple objects at once.

        used_ids ensures:
          No object participates in more than one committed rule in the same step
          (even if it STAYs).

        Produced objects:
          A rule may return produced objects. They are appended after all commits
          and are NOT processed during this step.
        """
        fired = False
        dissolve_after = False
        used_ids = set()

        snapshot = list(self._objects)  # stable snapshot of objects present at start of step
        to_add = []  # clones + produced objects (become eligible next step)

        for anchor in snapshot:
            # skip if anchor already used or moved away by a previous multi-rule
            if not self._available(anchor, used_ids):
                continue

            for rule in self._rules:
                match = self._match_rule_for_anchor(rule, anchor, snapshot, used_ids)
                if match is None:
                    continue

                # action committed
                result = rule.action(*match)
                signals, produced = self._parse_result(result, rule.arity, rule, match)

                # validate + queue produced
                self._validate_produced(produced)
                to_add.extend(produced)

                # mark used for all involved objects (even STAY)
                for obj in match:
                    used_ids.add(id(obj))

                # commit signals per object
                for obj, sig in zip(match, signals):
                    if sig._diss:
                        dissolve_after = True
                    self._commit_signal(obj, sig, to_add)

                fired = True
                break  # one rule per anchor-object per step (partners already marked used)

        # Add clones/produced objects AFTER rule application so they won't be processed this step
        self._objects.extend(to_add)

        if dissolve_after:
            self._pending_dissolve = True

        return fired

    # ──────────────────────────────────────────────────
    #  DISSOLVE
    # ──────────────────────────────────────────────────

    def _dissolve(self):
        if self._parent is None:
            raise RootDissolveError(self._name)

        # forward ALL region contents (active + buffered) to parent; update ownership
        for obj in self._objects + self._inbox + self._next_inbox:
            obj._membrane = self._parent

        self._parent._next_inbox.extend(self._objects)
        self._parent._next_inbox.extend(self._inbox)
        self._parent._next_inbox.extend(self._next_inbox)

        self._objects.clear()
        self._inbox.clear()
        self._next_inbox.clear()

        # re-parent children to parent
        for child in self._children:
            child._parent = self._parent
            self._parent._children.append(child)
        self._children.clear()

        # remove self
        self._parent._children.remove(self)
        self._parent = None
        self._rules = []
        self._last_fired = False

    # ── halting ───────────────────────────────────────
    def is_halted(self) -> bool:
        no_pending = not self._inbox and not self._next_inbox
        return (not self._last_fired) and no_pending and all(c.is_halted() for c in self._children)

    # ── display ───────────────────────────────────────
    def __repr__(self):
        return f"[{self._name}]  {self._objects} {self._inbox} {self._next_inbox}"

    def tree_str(self, indent: int = 0) -> str:
        pad = "    " * indent
        lines = [pad + repr(self)]
        for child in self._children:
            lines.append(child.tree_str(indent + 1))
        return "\n".join(lines)


# ══════════════════════════════════════════════════════
#  PSYSTEM
# ══════════════════════════════════════════════════════

class PSystem:
    def __init__(self, root: Membrane):
        self.root = root
        self._step_count = 0

    def run(self, verbose: bool = True, max_steps: int = 500) -> None:
        if verbose:
            print(f"  init:\n{self.root.tree_str(2)}")

        while self._step_count < max_steps:
            self._step_count += 1

            # Phase 1: flush (deliveries from last step become visible)
            self.root._flush_inbox()

            # Phase 2: apply rules (recursively), dissolve deferred inside step()
            fired = self.root.step()

            # Phase 3: commit deliveries (become visible next step)
            self.root._commit_deliveries()

            if fired and verbose:
                print(f"  step {self._step_count:>2}:\n{self.root.tree_str(2)}")

            if self.root.is_halted():
                break


# ══════════════════════════════════════════════════════
#  DEMOS / TESTS
# ══════════════════════════════════════════════════════

class Token(PObject):
    def __init__(self, count, k):
        super().__init__()
        self.count = count
        self.k = k
    def __repr__(self):
        return f"Token(count={self.count}, k={self.k})"


class OutputMem(Membrane):
    pass


class WorkMem(Membrane):
    def __init__(self, name: str, output: OutputMem):
        super().__init__(name)
        self.output = output
        self << output

    @when(lambda t: t.count >= t.k)
    def consume(self, t: Token):
        t.count -= t.k
        return self.stay()

    @when(lambda t: 0 < t.count < t.k)
    def send_down(self, t: Token):
        return self.into(self.output)

    @when(lambda t: t.count == 0)
    def discard(self, t: Token):
        return self.out()


def divisibility(n: int, k: int) -> None:
    print(f"\n{'═'*52}\n  divisibility(n={n}, k={k})\n{'═'*52}")
    mem2 = OutputMem("mem2")
    mem1 = WorkMem("mem1", mem2)
    mem1 += Token(n, k)
    PSystem(mem1).run()
    print(f"{'─'*52}")
    if not mem2._objects:
        print(f"  ✓  {n} IS divisible by {k}")
    else:
        print(f"  ✗  {n} NOT divisible by {k}  (remainder={mem2._objects[0].count})")
    print(f"{'═'*52}")




if __name__ == "__main__":
    divisibility(12, 3)
    divisibility(11, 2)
