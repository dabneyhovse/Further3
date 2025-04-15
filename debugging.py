from __future__ import annotations

import code
import os
import signal
import time
import traceback


def debug_callback(sig, frame):
    """Interrupt running process, and provide a python prompt for
    interactive debugging."""
    local_vars = {'_frame': frame}  # Allow access to frame object.
    local_vars.update(frame.f_globals)  # Unless shadowed by global
    local_vars.update(frame.f_locals)

    trace = traceback.format_stack(frame)

    match sig:
        case signal.SIGUSR1:
            console = code.InteractiveConsole(local_vars)
            message = ("Signal received: entering python shell.\n"
                       "Resume execution with Control-D / EOF\n"
                       "Traceback:\n" +
                       "".join(trace))
            console.interact(message)
            time.sleep(10)
        case signal.SIGUSR2:
            import sys
            print(
                "Signal received: dumping state.\n"
                "Traceback:\n" +
                "".join(trace) +
                "\n"
                "Local vars:\n" +
                "\n".join(f"{k}: {repr(v)}" for k, v in local_vars.items()),
                file=sys.stderr
            )


def listen():
    print(f"Execution pid: {os.getpid()}\nListening for intercepts.")
    signal.signal(signal.SIGUSR1, debug_callback)  # Attempt to create an interactive console (will often fail)
    signal.signal(signal.SIGUSR2, debug_callback)  # Attempt to create an interactive console (will often fail)


def intercept(pid: int, capture: bool) -> None:
    os.kill(pid, signal.SIGUSR1 if capture else signal.SIGUSR2)
    if capture:
        print("Resume execution with Control-D / EOF")


if __name__ == "__main__":
    intercept(int(input("pid: ")), input("capture? (y/n): ")[0].lower() == "y")
