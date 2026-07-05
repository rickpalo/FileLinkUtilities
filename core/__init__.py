"""File & Link Utilities core: pure-Python, bpy-free logic.

Nothing in this package may import ``bpy``. That keeps dependency-graph
building, content fingerprinting and report serialization unit-testable with
plain pytest outside of Blender. Operators in ``filelink.ops`` are the only
code allowed to touch ``bpy``; they gather data, hand it to ``core``, and apply
``core`` results back as mutations.
"""
