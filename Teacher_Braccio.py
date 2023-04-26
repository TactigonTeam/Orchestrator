import time
import sys
from os import path
import orchestrator_lib as lib
from typing import List
from multiprocessing.connection import Connection

CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))
sys.path.insert(0, path.join(CLIENT_PY_PATH, "TGear_Engine"))
sys.path.insert(0, path.dirname(__file__))

from Config_Manager import Config_Manager
from TGear_Engine import Phrase, HotWord
from Braccio_Orchestrator import Braccio_Msg_Command_List, Braccio_Msg_Command, Wrist_Status_Enum, Gripper_Status_Enum
from Macro_Braccio import Macro

class Teacher_Braccio:

    RUNNING = 1
    STOPPED = 3
    TIMEOUT_S = 25

    MODE_COMMAND = 1
    MODE_WAIT = 2

    def __init__(self, gesture_pipe: Connection, robot_pipe: Connection, voice_pipe: Connection, combo: bool = False, debug=False) -> None:
        """Teacher can register macro to a json file. It uses both gesture pipe and voice pipe to get commands.

        Args:
            gesture_pipe (Connection): Connection to get gestures from
            robot_pipe (Connection): Connection to send commands to IronBoy
            voice_pipe (Connection): Connection to get transcripts from
            combo (bool, optional): Define if the gesture pipe contains a combo gesture or a simple gesture. Combo if True. Defaults to False.
        """
        cfg = Config_Manager.from_file("apps/application_orchestrator_voice.json")
        braccio_config = cfg.get("braccio")
        voice_config = cfg.get("voice")
        teacher_config = voice_config["teacher"]
        lessons = cfg.get("lessons")
        steps_cfg = braccio_config["voice"]

        state = self.RUNNING
        mode = self.MODE_COMMAND

        lib.flush_pipe(gesture_pipe)
        lib.flush_pipe(robot_pipe)
        lib.flush_pipe(voice_pipe)

        if combo:
            gestures = braccio_config["combo_gestures"]["list"]
        else:
            gestures = braccio_config["gestures"]

        # print("Pronuncia la lezione desiderata:")
        lib.user_feedback(lib.FeedbackEnum.TEACHER_CHOOSE_LESSON)
        phrase_start = Phrase.from_config(teacher_config["save_phrase"])
        phrase_stop = Phrase.from_config(teacher_config["stop_phrase"])
        
        default_phrases = [phrase_start]
        lesson_phrases = [Phrase.from_config(lesson) for lesson in lessons]
        step_phrases = [Phrase.from_config(step) for step in steps_cfg]

        if debug:
            voice_pipe.send(default_phrases)
            voice_command = lesson_phrases[0]
        else:
            voice_command = lib.phrases_routine(voice_pipe, lesson_phrases + default_phrases)

        if voice_command != None:
            selected_lesson = voice_command.payload
            print(selected_lesson)
            macro_name = selected_lesson["file_name"]
            macro = Macro(macro_name)

            _t = 0

            lib.flush_pipe(gesture_pipe)
            lib.flush_pipe(robot_pipe)
            lib.flush_pipe(voice_pipe)
            
            # print(F"Ok! Ora puoi iniziare ad aggiungere comandi alla lezione '{selected_lesson['phrase']}' eseguendo gesture.")
            lib.user_feedback(lib.FeedbackEnum.TEACHER_LESSON_ACK)

            while state == self.RUNNING:

                if gesture_pipe.poll():
                    if mode == self.MODE_COMMAND:
                        command = None
                        if combo:
                            gesture_l, gesture_r = gesture_pipe.recv()
                            print(gesture_l, gesture_r)
                            for combo_gesture in gestures:
                                if combo_gesture["gesture_l"] == gesture_l and combo_gesture["gesture_r"] == gesture_r:
                                    command = combo_gesture
                            # print(command)
                        else:
                            gesture_l = "None"
                            gesture_r, device = gesture_pipe.recv()
                            print(gesture_r)
                            if gesture_r in gestures:
                                command = gestures[gesture_r]
                    
                        if command != None:

                            # iterations = 1
                            # command_text = command['command']

                            if not command["single"]:
                                # print("Quanti" , command["command"], "devo eseguire?")
                                # ironboy_feedback(robot_pipe, Ironboy_Feedback_Enum.EXPECT_VOICE_COMMAND, ball_grab)
                                lib.user_feedback(lib.FeedbackEnum.TEACHER_COMMAND_VOICE_PARAMETER)
                               
                                filtered_steps_phrases = [phrase for phrase in step_phrases if [gesture_l, gesture_r] in phrase.gestures]

                                voice_command = lib.phrases_routine(voice_pipe, filtered_steps_phrases + default_phrases)
                                # voice_command = lib.voice_routine(voice_pipe, [k for k in voce_to_number], timeout=10, retry=5)
                                
                                if voice_command in filtered_steps_phrases:

                                    if voice_command.payload["type"] == "number":
                                        delta = int(voice_command.payload["value"])

                                    elif voice_command.payload["type"] == "position":
                                        position = voice_command.payload["value"]
                                        command_msg_list = [Braccio_Msg_Command(*p) for p in braccio_config["positions"][position]]
                                        command_msg = Braccio_Msg_Command_List(command_msg_list)
                                    
                                    robot_pipe.send(command_msg)
                                    mode = self.MODE_WAIT
                                    _t = 0
                                else:
                                    # print("Il comando", command["command"], "necessit� di un numero di comandi da eseguire, prego ripeterlo.")
                                    lib.user_feedback(lib.FeedbackEnum.TEACHER_COMMAND_ERROR_VOICE_PARAMETER)
                        else:
                            # print("Ops! Il gesto che hai fatto non � presente tra le configurazioni...")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_GESTURE_NOT_IN_COMMAND)
                    else:
                        del_g = gesture_pipe.recv()
                        # print(F"Gesture sent before execution completed")
                        lib.user_feedback(lib.FeedbackEnum.TEACHER_CANNOT_SEND_COMMAND_WHILE_EXECUTING)
                        del del_g

                    lib.flush_pipe(gesture_pipe)

                if robot_pipe.poll():
                    returned_command_msg = robot_pipe.recv()
                    if mode == self.MODE_WAIT:
                        if returned_command_msg == command_msg:
                            _t = 0
                            lib.flush_pipe(gesture_pipe)
                            lib.flush_pipe(voice_pipe)
                            # print("reset:", _t)
                            if returned_command_msg.has_error:
                                # print("Error in ironboy command. Could not add command")
                                lib.user_feedback(lib.FeedbackEnum.TEACHER_BRACCIO_HAS_ERROR)
                                mode = self.MODE_COMMAND

                            if returned_command_msg.is_completed:
                                for cmd in returned_command_msg.command_list:
                                    macro.add_command(cmd)
                                mode = self.MODE_COMMAND
                        else:
                            # print(F"Error. Received {returned_command_msg} from Ironboy while waiting for {command_msg}")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_BRACCIO_COMMAND_MISMATCH)
                
                if voice_pipe.poll():
                    phrase = voice_pipe.recv()

                    # if teacher_config["save_command"] in transcript:
                    if phrase == phrase_start:
                        if mode == self.MODE_COMMAND:
                            # print("Sto salvando la macro, attendere...")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_SAVING_MACRO)
                            macro.save()
                            state = self.STOPPED
                            # print("Macro salvata!")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_MACRO_SAVED)
                        else:
                            # print("Non � possibile salvare la macro mentre un comando � in esecuzione")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_CANNOT_SAVE_MACRO_WHILE_COMMAND)
                    
                    # else:
                    #     print("Did not understand command - expected 'save'")

                if mode == self.MODE_WAIT:
                    
                    time.sleep(0.1)
                    _t += 0.1

                    # print("_t", _t)

                    if _t >= self.TIMEOUT_S:
                        # print("Ops! Non � stato possibile completare il controllo del comando inviato. Per favore ripeti il comando inviato...")
                        lib.user_feedback(lib.FeedbackEnum.TEACHER_COMMAND_TIMEOUT)
                        mode = self.MODE_COMMAND

        else:
            # print("Non � possibile identificare la lezione con i comandi inviati.")
            lib.user_feedback(lib.FeedbackEnum.TEACHER_CANNOT_FIND_LESSON)

        # print("Arrivederci e grazie!")


# def tgear(_pipe):
#     time.sleep(5)
#     _pipe.send(("push", "fakefake"))
#     time.sleep(5)
#     _pipe.send(("push", "fakefake"))

# def ironboyy(_pipe):

#     while not _pipe.poll():
#         msg = _pipe.recv()
#         time.sleep(msg.iterations if msg.iterations > 5 else 5)
#         msg.executed = True
#         _pipe.send(msg)

if __name__ == "__main__":

    from TGear_Engine import TGear_Engine, TGear_Pipes_Name
    from Config_Manager import Config_Manager
    from multiprocessing import Process, Pipe
    from Braccio_Orchestrator import Braccio
    from Gesture_Combo import Gesture_Combo


    tgear = TGear_Engine()
    tgear.config(tacti="RIGHT", gesture_pipe_en=True, voice_pipe_en=True)
    tgear.config(tacti="LEFT", gesture_pipe_en=True)
    
    tgear.start()

    voice_pipe = tgear.get_pipe("RIGHT", TGear_Pipes_Name.VOICE)

    gest_pipe_rx, pipe_combo_tx = Pipe(duplex=False)
    gesture_combo = Gesture_Combo(tgear.get_pipe("LEFT", TGear_Pipes_Name.GEST), tgear.get_pipe("RIGHT", TGear_Pipes_Name.GEST), pipe_combo_tx, debug=False)
    gesture_combo.start()

    orchestrator_cfg = Config_Manager.from_file("apps/application_orchestrator_voice.json")
    braccio_cfg = orchestrator_cfg.get("braccio")

    o_b, b_o = Pipe()

    braccio = Braccio(braccio_cfg, o_b)
    braccio.start()

    print("Connecting braccio")

    while not braccio.is_connected:
        time.sleep(1)

    print("braccio connected")

    t = Teacher_Braccio(gest_pipe_rx, b_o, voice_pipe, combo=True, debug=True)
    
    # t_p = Process(target=tgear, args=(pipe_t2,),)

    # while not ib.is_connected:
    #     time.sleep(1)
    #     print("connecting")

    # t_p.start()

    gesture_combo.stop()
    braccio.stop()
    tgear.stop()
    # t_p.terminate()
    # ib.terminate()