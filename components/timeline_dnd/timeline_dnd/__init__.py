import os
import streamlit.components.v1 as components

_RELEASE = True
if _RELEASE:
    _component_func = components.declare_component(
        "timeline_dnd",
        path=os.path.join(os.path.dirname(__file__), "..", "frontend"),
    )
else:
    _component_func = components.declare_component("timeline_dnd", url="http://localhost:3001")


def timeline_dnd(items, start, end, key=None):
    return _component_func(items=items, start=start, end=end, key=key, default=None)
