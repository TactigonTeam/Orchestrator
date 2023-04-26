import time
import sys
from os import path
import orchestrator_lib as lib
from multiprocessing.connection import Connection

CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))
sys.path.insert(0, path.join(CLIENT_PY_PATH, "TGear_Engine"))
sys.path.insert(0, path.dirname(__file__))


from Config_Manager import Config_Manager
from TGear_Engine import Phrase, HotWord
from IronBoy_Orchestrator import IronBoy_Msg_Command, ironboy_feedback, Ironboy_Feedback_Enum
from Macro import Macro

class Student:
    RUNNING = 1
    STOPPED = 3
    TIMEOUT_S = 15

    MODE_COMMAND = 1
    MODE_WAIT = 2

    def __init__(self, ironboy_pipe: Connection, voice_pipe: Connection):
        """Student loads a Macro and send it's command to the IronBoy object

        Args:
            ironboy_pipe (Connection): Connection to send commands to ironboy
            voice_pipe (Connection): Connection to gets speech transcripts from the speech recognition routine
        """
        cfg = Config_Manager.from_file("apps/application_orchestrator_voice.json")
        voice_config = cfg.get("voice")
        lessons = cfg.get("lessons")
        student_config = voice_config["student"]
        # voce_to_number = voice_config["number"]

        mode = Student.MODE_COMMAND

        lib.flush_pipe(ironboy_pipe)
        lib.flush_pipe(voice_pipe)

        # phrase_stop = Phrase([HotWord(hw["word"], hw["boost"]) for hw in student_config["stop_phrase"]["hot_words"]], is_default=True)
        # phrase_stop = Phrase([HotWord(hw["word"], hw["boost"]) for hw in student_config["stop_phrase"]["hot_words"]], timeout=student_config["stop_phrase"]["timeout"], retry=student_config["stop_phrase"]["retry"], is_default=True)
        phrase_stop = Phrase.from_config(student_config["stop_phrase"])
        default_phrases = [phrase_stop]

        # print("Pronuncia la lezione desiderata:")
        lib.user_feedback(lib.FeedbackEnum.STUDENT_CHOOSE_LESSON)
        # lesson_phrases = [Phrase([HotWord(hw["word"], hw["boost"]) for hw in lesson["hot_words"]], payload={"file_name": lesson["file_name"], "phrase": lesson["phrase"]}, timeout=lesson["timeout"], retry=lesson["retry"]) for lesson in lessons]
        lesson_phrases = [Phrase.from_config(lesson) for lesson in lessons]

        # voice_command = lib.voice_routine(voice_pipe, [k for k in voce_to_number], timeout=10, retry=5)
        voice_command = lib.phrases_routine(voice_pipe, lesson_phrases + default_phrases)

        if voice_command == None:
            # print("Non è possibile identificare la macro con i comandi inviati.")
            lib.user_feedback(lib.FeedbackEnum.STUDENT_CANNOT_FIND_LESSON)

            state = Student.STOPPED
        else:
            selected_lesson = voice_command.payload
            macro_name = selected_lesson["file_name"]
            macro_filename = macro_name + ".json"
            
            try:
                macro = Macro(macro_name, macro_filename)
                state = Student.RUNNING
                i = 0

                # print(F"Lezione '{selected_lesson['phrase']}' trovata! Inizio la sua esecuzione!")
                lib.user_feedback(lib.FeedbackEnum.STUDENT_LESSON_ACK)
            except:
                # print(F"Ops! La lezione '{selected_lesson['phrase']}' non � stata trovata...")
                lib.user_feedback(lib.FeedbackEnum.STUDENT_LESSON_FILE_NOT_FOUND)
                state = Student.STOPPED

        while state == Student.RUNNING:
            if i == len(macro.commands):
                state = Student.STOPPED
                ironboy_feedback(ironboy_pipe, Ironboy_Feedback_Enum.STUDENT_END)
                # print("La lezione � stata eseguita correttamente!")
                lib.user_feedback(lib.FeedbackEnum.STUDENT_LESSON_EXECUTED_CORRECTLY)
                break

            if mode == Student.MODE_COMMAND:
                command = macro.commands[i]
                command_msg = IronBoy_Msg_Command.from_macro_command(command)
                ironboy_pipe.send(command_msg)
                mode = Student.MODE_WAIT
                _t = 0

            if ironboy_pipe.poll():
                returned_command_msg = ironboy_pipe.recv() 
                if mode == Student.MODE_WAIT:
                    if returned_command_msg == command_msg:
                        _t = 0
                        if returned_command_msg.has_error:
                            # print("Error in ironboy command. Student stop")
                            lib.user_feedback(lib.FeedbackEnum.STUDENT_IRONBOY_HAS_ERROR)

                            break

                        if returned_command_msg.is_completed:
                            i += 1
                            mode = Student.MODE_COMMAND
                    else:
                        # print(F"Error. Received {returned_command_msg} from Ironboy while waiting for {command_msg}")
                        lib.user_feedback(lib.FeedbackEnum.STUDENT_IRONBOY_COMMAND_MISMATCH)
                    

            if voice_pipe.poll():
                phrase = voice_pipe.recv()
                if phrase == phrase_stop:
                    ironboy_pipe.send(IronBoy_Msg_Command.halt_command())
                    state = Student.STOPPED
                # else:
                #     print("Did not understand command - expected 'stop'")


            if mode == Student.MODE_WAIT:
                time.sleep(0.1)
                _t += 0.1

                if _t >= Student.TIMEOUT_S:
                    # print("Ops! Non � stato possibile completare il controllo del comando inviato. Meglio finire qui...")
                    lib.user_feedback(lib.FeedbackEnum.STUDENT_COMMAND_TIMEOUT)
                    ironboy_pipe.send(IronBoy_Msg_Command.halt_command())
                    state = Student.STOPPED


        # print("Grazie e arrivederci!")

# if __name__ == "__main__":
#     import sys
#     from os import path

#     CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
#     sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))

#     from Config_Manager import Config_Manager
#     from IronBoy import IronBoy
#     from multiprocessing import Pipe

#     pipe1, pipe2 = Pipe()

#     ib_cfg = Config_Manager.from_file("apps/application_orchestrator.json")
#     ib = IronBoy(ib_cfg, pipe1)
#     ib.start()

#     while not ib.is_connected:
#         time.sleep(1)
#         print("Connecting")

#     print("connected")

#     s = Student("bab", "bab.json", pipe2)
#     time.sleep(20)
#     ib.stop()