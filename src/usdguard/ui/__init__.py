"""Optional Qt user interface for usdguard.

Install it with the ``ui`` extra (``pip install "usdguard[ui]"``) and run
``usdguard-ui [STAGE]``. The UI uses the Qt.py shim, so it runs with
PySide6 or PySide2, including the binding a DCC already provides.

Validation runs in a worker thread that opens its own stage; the UI
thread only ever receives the immutable :class:`usdguard.core.Report`,
so no USD object crosses threads.
"""
