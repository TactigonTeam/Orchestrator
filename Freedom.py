import sys
from os import path
import orchestrator_lib as lib
from multiprocessing.connection import Connection

# Imports using Absolute Path
CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))
sys.path.insert(0, path.join(CLIENT_PY_PATH, "TGear_Engine"))
sys.path.insert(0, path.dirname(__file__))

from TGear_Engine import Phrase
from Config_Manager import Config_Manager
from IronBoy_Orchestrator import IronBoy_Msg_Command, IronBoy_Command_Enum, ironboy_feedback, Ironboy_Feedback_Enum

class Freedom:

    RUNNING = 1
    STOPPED = 2

    TICK_PERIOD_MS = 250

    def __init__(self, ironboy_pipe: Connection, angle_pipe_l: Connection, angle_pipe_r: Connection, voice_pipe: Connection):
        
        state = self.RUNNING

        config_file = Config_Manager.from_file("apps/application_orchestrator_voice.json")
        voice_config = config_file.get("voice")
        exit_phrase = Phrase.from_config(voice_config["freedom"]["exit_phrase"])

        if voice_pipe != False:
            voice_pipe.send([exit_phrase])

        ironboy = None
        angle_l = None
        angle_r = None
        voice = None
        tick = lib.millis()

        while state == self.RUNNING:

            if ironboy_pipe != False and ironboy_pipe.poll():
                ironboy = ironboy_pipe.recv()

            if angle_pipe_l != False and angle_pipe_l.poll():
                angle_l = angle_pipe_l.recv()
            
            if angle_pipe_r != False and angle_pipe_r.poll():
                angle_r = angle_pipe_r.recv()

            if voice_pipe != False and voice_pipe.poll():
                voice_cmd = voice_pipe.recv()
                if voice_cmd == exit_phrase:
                    ironboy_feedback(ironboy_pipe, Ironboy_Feedback_Enum.STUDENT_END)
                    state = self.STOPPED

            new_tick = lib.millis()

            if new_tick - tick > self.TICK_PERIOD_MS:
                tick = new_tick
                print(angle_l, angle_r)
                if angle_l != None and angle_r != None:
                    cmd_string = F"{angle_r[0]};{angle_r[1]};{angle_l[0]};{angle_l[1]};"
                    cmd = IronBoy_Msg_Command(cmd_string, command_type=IronBoy_Command_Enum.ANGLE.value)
                    ironboy_pipe.send(cmd)


if __name__ == "__main__":
    import time

    
    from TGear_Engine import TGear_Engine, TGear_Pipes_Name
    from multiprocessing import Process, Pipe

    from IronBoy_Orchestrator import IronBoy

    tgear = TGear_Engine()
    tgear.config(tacti="RIGHT", gesture_pipe_en=True, angle_pipe_en=True, voice_pipe_en=True)
    tgear.config(tacti="LEFT", gesture_pipe_en=True, angle_pipe_en=True)

    tgear.start()

    ib_pipe, freedom_pipe = Pipe()

    ib_cfg = Config_Manager.from_file("apps/application_orchestrator_voice.json")
    ib = IronBoy(ib_cfg.get("ironboy"), ib_pipe)
    ib.start()

    voice_pipe = tgear.get_pipe("RIGHT", TGear_Pipes_Name.VOICE)
    angle_pipe_r = tgear.get_pipe("RIGHT", TGear_Pipes_Name.ANGLE)
    angle_pipe_l = tgear.get_pipe("LEFT", TGear_Pipes_Name.ANGLE)

    gest_pipe_r = tgear.get_pipe("RIGHT", TGear_Pipes_Name.GEST)
    gest_pipe_l = tgear.get_pipe("LEFT", TGear_Pipes_Name.GEST)

    g_l = Process(target=lib.flush_pipe, args=(gest_pipe_l,))
    g_r = Process(target=lib.flush_pipe, args=(gest_pipe_r,))

    g_l.start()
    g_r.start()

    while not ib.is_connected:
        print("wait ib")
        time.sleep(2)

    f = Freedom(freedom_pipe, angle_pipe_l, angle_pipe_r, voice_pipe)

    tgear.stop()
    ib.terminate()
    g_l.terminate()
    g_r.terminate()
