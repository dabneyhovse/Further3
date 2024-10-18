from __future__ import annotations

import code
import os
import signal
import time
import traceback


def debug_callback(_sig, frame):
    """Interrupt running process, and provide a python prompt for
    interactive debugging."""
    local_vars = {'_frame': frame}  # Allow access to frame object.
    local_vars.update(frame.f_globals)  # Unless shadowed by global
    local_vars.update(frame.f_locals)

    console = code.InteractiveConsole(local_vars)
    message = ("Signal received: entering python shell.\n"
               "Resume execution with Control-D / EOF\n"
               "Traceback:\n" +
               "".join(traceback.format_stack(frame)))
    console.interact(message)
    time.sleep(10)


def listen():
    print(f"Execution pid: {os.getpid()}\nListening for intercepts.")
    signal.signal(signal.SIGUSR1, debug_callback)  # Register handler


def intercept(pid: int) -> None:
    os.kill(pid, signal.SIGUSR1)
    print("Resume execution with Control-D / EOF")


if __name__ == "__main__":
    intercept(int(input("pid: ")))
