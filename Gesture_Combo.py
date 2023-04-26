import sys
from os import path
import time
from multiprocessing import Process
from multiprocessing.connection import Connection

CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))

from Config_Manager import Config_Manager

class Gesture_Combo(Process):

    def __init__(self, gest_pipe_l: Connection, gest_pipe_r: Connection, combo_pipe: Connection, debug: bool = False) -> None:
        """Gesture_Combo combines two pipes from left and right TSkins, in order to produce a combo gesture. This is a subclass of Process.

        Args:
            gest_pipe_l (Connection): Left gesture pipe from TSkin
            gest_pipe_r (Connection): Right gesture pipe from TSkin
            combo_pipe (Connection): Pipe to send combined gesture into
            debug (bool, optional): If True prints in console the combined gesture that are sent. Defaults to False.
        """
        super(Gesture_Combo, self).__init__(
            target=self._loop,
            args=(gest_pipe_l, gest_pipe_r, combo_pipe, debug)
        )

    def _loop(self, gest_pipe_l: Connection, gest_pipe_r: Connection, combo_pipe: Connection, debug: bool) -> None:

        cfg = Config_Manager.from_file("apps/application_orchestrator_voice.json")
        TIMEOUT_MS = cfg.get("ironboy")["combo_gestures"]["wait_ms"]
        
        while True:
            if gest_pipe_l.poll():
                time.sleep(TIMEOUT_MS / 1000)
            elif gest_pipe_r.poll():
                time.sleep(TIMEOUT_MS / 1000)
            else:
                continue

            gesture_l, gesture_r = "None", "None"

            if gest_pipe_l.poll():
                gesture_l, device_l = gest_pipe_l.recv()

            if gest_pipe_r.poll():
                gesture_r, device_r = gest_pipe_r.recv()

            combo_pipe.send((gesture_l, gesture_r))
            if debug:
                print(gesture_l, gesture_r)

    def stop(self):
        return Process.terminate(self)


if __name__ == "__main__":

    import sys
    from os import path
    from multiprocessing import Pipe

    CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
    sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))
    sys.path.insert(0, path.join(CLIENT_PY_PATH, "TGear_Engine"))

    from Config_Manager import Config_Manager
    from TGear_Engine import TGear_Engine, TGear_Pipes_Name, TGear_Connection_Status

    t = TGear_Engine()
    t.config("RIGHT", gesture_pipe_en=True)
    t.config("LEFT", gesture_pipe_en=True)

    pipe_l = t.get_pipe("LEFT", TGear_Pipes_Name.GEST)
    pipe_r = t.get_pipe("RIGHT", TGear_Pipes_Name.GEST)

    pipe_combo_rx, pipe_combo_tx = Pipe(duplex=False)

    t.start()
    c = Gesture_Combo(pipe_l, pipe_r, pipe_combo_tx, debug=True)
    c.start()

    input()

    c.stop()
    t.stop()