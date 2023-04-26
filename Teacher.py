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
from IronBoy_Orchestrator import IronBoy_Msg_Command, ironboy_feedback, Ironboy_Feedback_Enum
from Macro import Macro

class Teacher:

    RUNNING = 1
    STOPPED = 3
    TIMEOUT_S = 25

    MODE_COMMAND = 1
    MODE_WAIT = 2

    def __init__(self, gesture_pipe: Connection, ironboy_pipe: Connection, voice_pipe: Connection, combo: bool = False) -> None:
        """Teacher can register macro to a json file. It uses both gesture pipe and voice pipe to get commands.

        Args:
            gesture_pipe (Connection): Connection to get gestures from
            ironboy_pipe (Connection): Connection to send commands to IronBoy
            voice_pipe (Connection): Connection to get transcripts from
            combo (bool, optional): Define if the gesture pipe contains a combo gesture or a simple gesture. Combo if True. Defaults to False.
        """
        cfg = Config_Manager.from_file("apps/application_orchestrator_voice.json")
        ironboy_config = cfg.get("ironboy")
        voice_config = cfg.get("voice")
        teacher_config = voice_config["teacher"]
        lessons = cfg.get("lessons")
        steps_cfg = ironboy_config["voice"]

        state = Teacher.RUNNING
        mode = Teacher.MODE_COMMAND

        ball_grab = False

        lib.flush_pipe(gesture_pipe)
        lib.flush_pipe(ironboy_pipe)
        lib.flush_pipe(voice_pipe)

        if combo:
            gestures = ironboy_config["combo_gestures"]["list"]
        else:
            gestures = ironboy_config["gestures"]

        # print("Pronuncia la lezione desiderata:")
        lib.user_feedback(lib.FeedbackEnum.TEACHER_CHOOSE_LESSON)
        # voice_command = lib.voice_routine(voice_pipe, [k for k in voce_to_number], timeout=10, retry=5)
        # phrase_start = Phrase([HotWord(hw["word"], hw["boost"]) for hw in teacher_config["save_phrase"]["hot_words"]], timeout=teacher_config["save_phrase"]["timeout"], retry=teacher_config["save_phrase"]["retry"], is_default=True)
        # phrase_stop = Phrase([HotWord(hw["word"], hw["boost"]) for hw in teacher_config["stop_phrase"]["hot_words"]], timeout=teacher_config["stop_phrase"]["timeout"], retry=teacher_config["stop_phrase"]["retry"], is_default=True)
        phrase_start = Phrase.from_config(teacher_config["save_phrase"])
        phrase_stop = Phrase.from_config(teacher_config["stop_phrase"])
        
        default_phrases = [phrase_start, phrase_stop]

        # lesson_phrases = [Phrase([HotWord(hw["word"], hw["boost"]) for hw in lesson["hot_words"]], payload={"file_name": lesson["file_name"], "phrase": lesson["phrase"]}, timeout=lesson["timeout"], retry=lesson["retry"]) for lesson in lessons]
        # step_phrases = [Phrase([HotWord(hw["word"], hw["boost"]) for hw in step["hot_words"]], payload={"number": step["number"]}, timeout=step["timeout"], retry=step["retry"]) for step in steps_cfg]
        lesson_phrases = [Phrase.from_config(lesson) for lesson in lessons]
        step_phrases = [Phrase.from_config(step) for step in steps_cfg]

        voice_command = lib.phrases_routine(voice_pipe, lesson_phrases + default_phrases)

        if voice_command != None:
            selected_lesson = voice_command.payload
            print(selected_lesson)
            macro_name = selected_lesson["file_name"]
            macro = Macro(macro_name)
            ball_grab = False

            _t = 0

            lib.flush_pipe(gesture_pipe)
            lib.flush_pipe(ironboy_pipe)
            lib.flush_pipe(voice_pipe)
            
            # print(F"Ok! Ora puoi iniziare ad aggiungere comandi alla lezione '{selected_lesson['phrase']}' eseguendo gesture.")
            lib.user_feedback(lib.FeedbackEnum.TEACHER_LESSON_ACK)

            while state == Teacher.RUNNING:

                if gesture_pipe.poll():
                    if mode == Teacher.MODE_COMMAND:
                        command = None
                        if combo:
                            gesture_l, gesture_r = gesture_pipe.recv()
                            print(gesture_l, gesture_r)
                            for combo_gesture in gestures:
                                if combo_gesture["gesture_l"] == gesture_l and combo_gesture["gesture_r"] == gesture_r:
                                    command = combo_gesture
                            # print(command)
                        else:
                            gesture, device = gesture_pipe.recv()
                            print(gesture)
                            if gesture in gestures:
                                command = gestures[gesture]
                    
                        if command != None:

                            iterations = 1
                            command_text = command['command']

                            if not command["single"]:
                                # print("Quanti" , command["command"], "devo eseguire?")
                                ironboy_feedback(ironboy_pipe, Ironboy_Feedback_Enum.EXPECT_VOICE_COMMAND, ball_grab)
                                lib.user_feedback(lib.FeedbackEnum.TEACHER_COMMAND_VOICE_PARAMETER)
                               
                                filtered_steps_phrases = [phrase for phrase in step_phrases if [gesture_l, gesture_r] in phrase.gestures]

                                voice_command = lib.phrases_routine(voice_pipe, filtered_steps_phrases)
                                # voice_command = lib.voice_routine(voice_pipe, [k for k in voce_to_number], timeout=10, retry=5)
                                
                                if voice_command in filtered_steps_phrases:
                                    try:
                                        ball_grab = voice_command.payload["ball_grab"]
                                    except:
                                        pass

                                    if voice_command.payload["type"] == "number":
                                        iterations = int(voice_command.payload["value"])
                                    elif voice_command.payload["type"] == "command":
                                        command_text = voice_command.payload["value"]
                                        iterations = 1
                                    else:
                                        iterations = 0
                                else:
                                    iterations = 0

                            if iterations > 0:
                                command_msg = IronBoy_Msg_Command(command_text, iterations)
                                ironboy_pipe.send(command_msg)
                                mode = Teacher.MODE_WAIT
                                _t = 0
                            else:
                                # print("Il comando", command["command"], "necessit� di un numero di comandi da eseguire, prego ripeterlo.")
                                ironboy_feedback(ironboy_pipe, Ironboy_Feedback_Enum.VOICE_NOT_FOUND, ball_grab)
                                lib.user_feedback(lib.FeedbackEnum.TEACHER_COMMAND_ERROR_VOICE_PARAMETER)
                                voice_pipe.send(default_phrases)
                        else:
                            # print("Ops! Il gesto che hai fatto non � presente tra le configurazioni...")
                            ironboy_feedback(ironboy_pipe, Ironboy_Feedback_Enum.GESTURE_NOT_FOUND, ball_grab)
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_GESTURE_NOT_IN_COMMAND)
                    else:
                        del_g = gesture_pipe.recv()
                        # print(F"Gesture sent before execution completed")
                        lib.user_feedback(lib.FeedbackEnum.TEACHER_CANNOT_SEND_COMMAND_WHILE_EXECUTING)
                        del del_g

                    lib.flush_pipe(gesture_pipe)

                if ironboy_pipe.poll():
                    returned_command_msg = ironboy_pipe.recv()
                    if mode == Teacher.MODE_WAIT:
                        if returned_command_msg == command_msg:
                            _t = 0
                            lib.flush_pipe(gesture_pipe)
                            lib.flush_pipe(voice_pipe)
                            # print("reset:", _t)
                            if returned_command_msg.has_error:
                                mode = Teacher.MODE_COMMAND
                                # print("Error in ironboy command. Could not add command")
                                lib.user_feedback(lib.FeedbackEnum.TEACHER_IRONBOY_HAS_ERROR)

                            if returned_command_msg.is_completed:
                                macro.add_command(returned_command_msg)
                                mode = Teacher.MODE_COMMAND
                        else:
                            # print(F"Error. Received {returned_command_msg} from Ironboy while waiting for {command_msg}")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_IRONBOY_COMMAND_MISMATCH)
                
                if voice_pipe.poll():
                    phrase = voice_pipe.recv()

                    # if teacher_config["save_command"] in transcript:
                    if phrase == phrase_start:
                        if mode == Teacher.MODE_COMMAND:
                            # print("Sto salvando la macro, attendere...")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_SAVING_MACRO)
                            macro.save()
                            state = Teacher.STOPPED
                            # print("Macro salvata!")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_MACRO_SAVED)
                        else:
                            # print("Non � possibile salvare la macro mentre un comando � in esecuzione")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_CANNOT_SAVE_MACRO_WHILE_COMMAND)
                    
                    # elif teacher_config["stop_command"] in transcript:
                    elif phrase == phrase_stop:
                        if mode == Teacher.MODE_WAIT:
                            # print("Interrompo il comando. Questo comando non verr� salvato nella macro.")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_STOP_COMMAND)
                            ironboy_pipe.send(IronBoy_Msg_Command.halt_command())
                            mode = Teacher.MODE_COMMAND
                        else:
                            # print("Non posso interrompere un comando perch� non c'� un comando in esecuzione")
                            lib.user_feedback(lib.FeedbackEnum.TEACHER_NO_COMMAND_TO_STOP)
                    # else:
                    #     print("Did not understand command - expected 'stop'")

                if mode == Teacher.MODE_WAIT:
                    
                    time.sleep(0.1)
                    _t += 0.1

                    # print("_t", _t)

                    if _t >= Teacher.TIMEOUT_S:
                        # print("Ops! Non � stato possibile completare il controllo del comando inviato. Per favore ripeti il comando inviato...")
                        lib.user_feedback(lib.FeedbackEnum.TEACHER_COMMAND_TIMEOUT)
                        ironboy_pipe.send(IronBoy_Msg_Command.halt_command())
                        mode = Teacher.MODE_COMMAND


        else:
            # print("Non � possibile identificare la lezione con i comandi inviati.")
            lib.user_feedback(lib.FeedbackEnum.TEACHER_CANNOT_FIND_LESSON)

        # print("Arrivederci e grazie!")


# def tgear(_pipe):
#     time.sleep(5)
#     _pipe.send(("push", "fakefake"))
#     time.sleep(5)
#     _pipe.send(("push", "fakefake"))

def ironboyy(_pipe):

    while not _pipe.poll():
        msg = _pipe.recv()
        time.sleep(msg.iterations if msg.iterations > 5 else 5)
        msg.executed = True
        _pipe.send(msg)

if __name__ == "__main__":

    from TGear_Engine import TGear_Engine, TGear_Pipes_Name
    from Config_Manager import Config_Manager
    from multiprocessing import Process, Pipe

    tgear = TGear_Engine()
    tgear.config(tacti="RIGHT", voice_pipe_en=True)

    tgear.start()

    # ib_cfg = Config_Manager.from_file("apps/application_orchestrator.json")
    # ib = IronBoy(ib_cfg, pipe_ib2)
    # ib.start()

    # gesturess = ib_cfg.get("gestures")
    gestures = None

    gesture_pipe, pipe_gesture = Pipe()
    ironboy_pipe, pipe_ironboy = Pipe()
    voice_pipe = tgear.get_pipe("RIGHT", TGear_Pipes_Name.VOICE)
    
    # t_p = Process(target=tgear, args=(pipe_t2,),)

    # while not ib.is_connected:
    #     time.sleep(1)
    #     print("connecting")

    # t_p.start()

    t = Teacher(gesture_pipe, ironboy_pipe, voice_pipe)

    tgear.stop()
    # t_p.terminate()
    # ib.terminate()