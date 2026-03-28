# PMembranes
=======================================================================
PMembranes
This is a **deterministic, sequential** simulator inspired by *transition P systems*.
It is NOT a full formal replica (e.g., no maximal parallelism), but it preserves
core ideas :

Core model
-------------------------
• Membranes form a rooted tree (no cycles, no DAG: each membrane has at most one parent). 

• Each membrane holds a multiset-like bag of objects (Python list; order ignored for matching). 

• Objects are **owned** by exactly one membrane at a time (tracked via PObject._membrane). 

• Rules act on objects and can :

    - STAY (possibly after mutating the object)
    - VANISH
    - OUT (move to parent)
    - INTO(child) or INTO() random child
    - CLONE (deepcopy N clones)
    - DISSOLVE (VANISH.dissolve) to dissolve the membrane after the step


Step semantics (3 global phases)
-------------------------------
For each global step:
  1) Flush:   _inbox  -> _objects   (objects delivered last step become visible now)
  2) Evolve:  apply rules to objects in each membrane (then recurse into children),
             and execute pending dissolutions after children are stepped.
  3) Commit:  _next_inbox -> _inbox (deliveries become visible next step)

Why two inboxes?
----------------
To guarantee: if an object is sent OUT/INTO during step N, it is NOT visible to rules
until step N+1. We deliver into _next_inbox, then commit it into _inbox at end of step.

Rule authoring (OOP style)
--------------------------
You define rules as methods in a Membrane subclass using the global decorator @when(guard).

• The guard signature must match the rule arity:
    - Single-object rule: guard(obj) -> bool
    - Multi-object rule:  guard(a, b, c, ...) -> bool

• The action method signature determines arity:
    - def r(self, obj: Token)              -> arity 1
    - def r(self, a: Sym, b: Sym, c: Sym)  -> arity 3

Type dispatch:
--------------
The engine reads method parameter annotations and uses them as type filters. Example:

    @when(lambda t: t.count > 0)
    def consume(self, t: Token): ...

Only Token instances are considered for that parameter.

Action return values
--------------------
Single-object rule (arity=1) may return:
    1) Signal
    2) (Signal, produced_list)

Multi-object rule (arity=N) may return:
    1) iterable of N Signals (e.g., [OUT, VANISH] or (OUT, VANISH))
    2) (signals_iterable, produced_list)

Produced objects:
-----------------
• produced_list contains NEW PObject instances to be added to the SAME membrane.
• Produced objects are appended after rule application, so they are NOT processed
  during the same step (they become eligible next global step).

Important operational policy
----------------------------
• "One rule per object per step": once an object participates in a committed rule
  (even STAY), it will not participate in any other rule in the same step.
• Multi-object rules match as a multiset: object list order does NOT matter.

"""
