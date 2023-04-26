import sys
import time
from os import path
from multiprocessing import Pipe
from enum import Enum

# Imports using Absolute Path
CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))
sys.path.insert(0, path.join(CLIENT_PY_PATH, "TGear_Engine"))
sys.path.insert(0, path.dirname(__file__))

import orchestrator_lib as lib

from Config_Manager import Config_Manager
from TGear_Engine import TGear_Engine, TGear_Pipes_Name, TGear_Connection_Status, Phrase, HotWord
from IronBoy_Orchestrator import IronBoy
from Braccio_Orchestrator import Braccio
from Teacher import Teacher
from Teacher_Braccio import Teacher_Braccio
from Student import Student
from Student_Braccio import Student_Braccio
from Freedom import Freedom
from Gesture_Combo import Gesture_Combo


class Orchestrator:

    RUNNING = 1
    STOPPING = 2
    STOPPED = 3

    MODE_TEACHER = 1
    MODE_STUDENT = 2
    MODE_EXIT = 3

    TIMEOUT_S = 20

    VERSION_MAX = 1
    VERSION_MIDDLE = 0
    VERSION_MIN = 3
    VERSION_DATE = "23/12/2022"

    # dict_voice_to_mode = {
    #     "teacher": 1,
    #     "student": 2,
    #     "exit": 3,
    # }

    def __init__(self):

        print("Application orchestrator version", self.VERSION_MAX, ".", self.VERSION_MIDDLE, ".", self.VERSION_MIN, " date:", self.VERSION_DATE)

        config_file = Config_Manager.from_file("apps/application_orchestrator_voice.json")
        
        ironboy_config = config_file.get("ironboy")
        braccio_config = config_file.get("braccio")
        voice_config = config_file.get("voice")
        orchestrator_voice_config = voice_config["orchestrator"]
        phrases_to_mode = orchestrator_voice_config["mode_selection_phrases"]
        combo = config_file.get("use_combo_gestures")
        robot = lib.Orchestrator_Robot_Enum(config_file.get("robot"))
        
        state = self.RUNNING

        if robot == lib.Orchestrator_Robot_Enum.IRONBOY:
            orchestrator_ironboy, ironboy_orchestrator = Pipe()
        elif robot == lib.Orchestrator_Robot_Enum.BRACCIO:
            orchestrator_braccio, braccio_orchestrator = Pipe()

        tgear = TGear_Engine()

        if tgear.enables["RIGHT"]:
            tgear.config(tacti="RIGHT", gesture_pipe_en=True, angle_pipe_en=True, voice_pipe_en=True)
        
        if tgear.enables["LEFT"]:
            tgear.config(tacti="LEFT", gesture_pipe_en=True, angle_pipe_en=True)

        voice_pipe = tgear.get_pipe("RIGHT", TGear_Pipes_Name.VOICE)

        if combo:
            if tgear.enables["RIGHT"] and tgear.enables["LEFT"]:
                gest_pipe_rx, pipe_combo_tx = Pipe(duplex=False)
                gesture_combo = Gesture_Combo(tgear.get_pipe("LEFT", TGear_Pipes_Name.GEST), tgear.get_pipe("RIGHT", TGear_Pipes_Name.GEST), pipe_combo_tx, debug=False)
                angle_pipe_l = tgear.get_pipe("LEFT", TGear_Pipes_Name.ANGLE)
                angle_pipe_r = tgear.get_pipe("RIGHT", TGear_Pipes_Name.ANGLE)
            else:
                # print("Error. Orchestrator is set to combo but only one TSkin device is configured in hal.json")
                lib.user_feedback(lib.FeedbackEnum.ORCHESTRATOR_COMBO_CONFIG_ERROR)
                return None
        else:
            if tgear.enables["RIGHT"]:
                gest_pipe_rx = tgear.get_pipe("RIGHT", TGear_Pipes_Name.GEST)
                angle_pipe_r = tgear.get_pipe("RIGHT", TGear_Pipes_Name.ANGLE)
                angle_pipe_l = False
            elif tgear.enables["LEFT"]:
                gest_pipe_rx = tgear.get_pipe("LEFT", TGear_Pipes_Name.GEST)
                angle_pipe_l = tgear.get_pipe("LEFT", TGear_Pipes_Name.ANGLE)
                angle_pipe_r = False
            else:
                # print("Error. Orchestrator no device enabled in hal.json")
                lib.user_feedback(lib.FeedbackEnum.ORCHESTRATOR_NO_DEVICE_ENABLED)
                return None

        tgear.start()

        if combo:
            gesture_combo.start()

        if robot == lib.Orchestrator_Robot_Enum.IRONBOY:
            ironboy = IronBoy(ironboy_config, ironboy_orchestrator)
            ironboy.start()
        elif robot == lib.Orchestrator_Robot_Enum.BRACCIO:
            braccio = Braccio(braccio_config, braccio_orchestrator)
            braccio.start()

        while True:
            tgear_conn_status = tgear.connection_status()
            if (combo and tgear_conn_status == (TGear_Connection_Status.CONNECTED, TGear_Connection_Status.CONNECTED)) \
                or \
                (not combo and TGear_Connection_Status.CONNECTED in tgear_conn_status ):
                break

            # print("Waiting for TSkin(s) connection")
            lib.user_feedback(lib.FeedbackEnum.ORCHESTRATOR_WAIT_TSKIN)
            time.sleep(2)

        if robot == lib.Orchestrator_Robot_Enum.IRONBOY:
            while not ironboy.is_connected:
                # print("Waiting for Ironboy connection")
                lib.user_feedback(lib.FeedbackEnum.ORCHESTRATOR_WAIT_IRONBOY)
                time.sleep(2)
        elif robot == lib.Orchestrator_Robot_Enum.BRACCIO:
            while not braccio.is_connected:
                # print("Waiting for Ironboy connection")
                lib.user_feedback(lib.FeedbackEnum.ORCHESTRATOR_WAIT_BRACCIO)
                time.sleep(2)

        lib.user_feedback(lib.FeedbackEnum.ORCHESTRATOR_INIT_MSG)

        # init state for voice detection
        # init_phrase = Phrase([HotWord(hw["word"], hw["boost"]) for hw in orchestrator_voice_config["init_phrase"]["hot_words"]], timeout=orchestrator_voice_config["init_phrase"]["timeout"], retry=orchestrator_voice_config["init_phrase"]["retry"], is_default=True)
        init_phrase = Phrase.from_config(orchestrator_voice_config["init_phrase"])
        voice_pipe.send([init_phrase])

        # Loads all the preconfigured words
        # phrase_teacher = Phrase([HotWord(hw["word"], hw["boost"]) for hw in phrases_to_mode["teacher"]["hot_words"]], timeout=phrases_to_mode["teacher"]["timeout"], retry=phrases_to_mode["teacher"]["retry"])
        # phrase_student = Phrase([HotWord(hw["word"], hw["boost"]) for hw in phrases_to_mode["student"]["hot_words"]], timeout=phrases_to_mode["student"]["timeout"], retry=phrases_to_mode["student"]["retry"])
        # phrase_exit = Phrase([HotWord(hw["word"], hw["boost"]) for hw in phrases_to_mode["exit"]["hot_words"]], timeout=phrases_to_mode["exit"]["timeout"], retry=phrases_to_mode["exit"]["retry"])

        phrase_teacher = Phrase.from_config(phrases_to_mode["teacher"])
        phrase_student = Phrase.from_config(phrases_to_mode["student"])
        phrase_freedom = Phrase.from_config(phrases_to_mode["freedom"])
        phrase_exit = Phrase.from_config(phrases_to_mode["exit"])

        angle_flusher_l = lib.PipeFlusher(angle_pipe_l)
        angle_flusher_r = lib.PipeFlusher(angle_pipe_r)
        gesture_flusher = lib.PipeFlusher(gest_pipe_rx)

        angle_flusher_l.start()
        angle_flusher_r.start()
        gesture_flusher.start()

        # while self.state.value == Orchestrator.RUNNING:
        while state == Orchestrator.RUNNING:

            if voice_pipe.poll():
                init_transcript = voice_pipe.recv()
                if init_transcript == init_phrase:
                    # I've said wake up tgear, must choose a mode
                    # print("Eccomi! In che modalità vuoi andare?")
                    lib.user_feedback(lib.FeedbackEnum.CHOOSE_MODE)
                    voice_command = lib.phrases_routine(voice_pipe, [phrase_teacher, phrase_student, phrase_freedom, phrase_exit])

                    if voice_command == phrase_teacher:
                        #print("teacher")
                        gesture_flusher.stop()
                        
                        if robot == lib.Orchestrator_Robot_Enum.IRONBOY:
                            t = Teacher(gest_pipe_rx, orchestrator_ironboy, voice_pipe, combo=combo)
                        elif robot == lib.Orchestrator_Robot_Enum.BRACCIO:
                            t = Teacher_Braccio(gest_pipe_rx, orchestrator_braccio, voice_pipe, combo=combo)

                        gesture_flusher.restart()
                        del t
                    elif voice_command == phrase_student:
                        # print("student")
                        if robot == lib.Orchestrator_Robot_Enum.IRONBOY:
                            s = Student(orchestrator_ironboy, voice_pipe)
                        elif robot == lib.Orchestrator_Robot_Enum.BRACCIO:
                            s = Student_Braccio(orchestrator_braccio, voice_pipe)
                        
                        del s
                    elif voice_command == phrase_freedom:
                        angle_flusher_l.stop()
                        angle_flusher_r.stop()
                        f = Freedom(orchestrator_ironboy, angle_pipe_l, angle_pipe_r, voice_pipe)
                        angle_flusher_l.restart()
                        angle_flusher_r.restart()
                        del f
                    elif voice_command == phrase_exit:
                        state = Orchestrator.MODE_EXIT
                    else:
                        # print("Non ho capito")
                        lib.user_feedback(lib.FeedbackEnum.DIDNT_UNDERSTAND)
                        pass

                    voice_pipe.send([init_phrase])
                
                else:
                    # print("Non ho capito 'wake up tgear'")
                    lib.user_feedback(lib.FeedbackEnum.DIDNT_UNDERSTAND_TGEAR)
                    voice_pipe.send([init_phrase])

        if combo:
            gesture_combo.stop()

        angle_flusher_l.terminate()
        angle_flusher_r.terminate()
        gesture_flusher.terminate()

        if robot == lib.Orchestrator_Robot_Enum.IRONBOY:
            ironboy.stop()
        elif robot == lib.Orchestrator_Robot_Enum.BRACCIO:
            braccio.stop()
        tgear.stop()

        state = Orchestrator.STOPPED
        lib.user_feedback(lib.FeedbackEnum.ORCHESTRATOR_STOPPED)
        # print(F"Orchestrator stopped")


def run() -> None:
    orchestrator = Orchestrator()


if __name__ == "__main__":
    run()

