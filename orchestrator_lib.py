import time
from enum import Enum
from typing import Union, List
from multiprocessing import Process, Value
from multiprocessing.connection import Connection

class Orchestrator_Robot_Enum(Enum):
    IRONBOY = "ironboy"
    BRACCIO = "braccio"

class FeedbackEnum(Enum):
    CHOOSE_MODE = 1
    DIDNT_UNDERSTAND = 2
    DIDNT_UNDERSTAND_TGEAR = 3

    ORCHESTRATOR_STOPPED = 100
    ORCHESTRATOR_COMBO_CONFIG_ERROR = 101
    ORCHESTRATOR_NO_DEVICE_ENABLED = 102
    ORCHESTRATOR_WAIT_TSKIN = 103
    ORCHESTRATOR_WAIT_IRONBOY = 104
    ORCHESTRATOR_WAIT_BRACCIO = 105
    ORCHESTRATOR_INIT_MSG = 106

    TEACHER_CHOOSE_LESSON = 200
    TEACHER_LESSON_ACK = 201
    TEACHER_COMMAND_VOICE_PARAMETER = 202
    TEACHER_COMMAND_ERROR_VOICE_PARAMETER = 203
    TEACHER_CANNOT_SEND_COMMAND_WHILE_EXECUTING = 214
    TEACHER_GESTURE_NOT_IN_COMMAND = 204
    TEACHER_IRONBOY_HAS_ERROR = 205
    TEACHER_IRONBOY_COMMAND_MISMATCH = 206
    TEACHER_SAVING_MACRO = 207
    TEACHER_MACRO_SAVED = 208
    TEACHER_CANNOT_SAVE_MACRO_WHILE_COMMAND = 209
    TEACHER_STOP_COMMAND = 210
    TEACHER_NO_COMMAND_TO_STOP = 211
    TEACHER_COMMAND_TIMEOUT = 212
    TEACHER_CANNOT_FIND_LESSON = 213
    TEACHER_BRACCIO_HAS_ERROR = 215
    TEACHER_BRACCIO_COMMAND_MISMATCH = 216

    STUDENT_CHOOSE_LESSON = 200
    STUDENT_LESSON_ACK = 305
    STUDENT_CANNOT_FIND_LESSON = 213
    STUDENT_LESSON_FILE_NOT_FOUND = 301
    STUDENT_LESSON_EXECUTED_CORRECTLY = 302
    STUDENT_IRONBOY_HAS_ERROR = 303
    STUDENT_IRONBOY_COMMAND_MISMATCH = 206
    STUDENT_COMMAND_TIMEOUT = 304
    STUDENT_BRACCIO_HAS_ERROR = 306
    STUDENT_BRACCIO_COMMAND_MISMATCH = 307

    IRONBOY_CONNECTED = 400
    IRONBOY_NOT_CONNECTED = 401
    IRONBOY_CONNECTION_ERROR = 402
    IRONBOY_DISCONNECTING = 403
    IRONBOY_DISCONNECTED = 404

    VOICE_TIMEOUT = 500
    VOICE_DID_NOT_FOUND_ANYTHING = 501
    VOICE_LISTENING_START = 503
    VOICE_LISTENING_STOP = 504
    VOICE_COMMAND_FOUND = 505


FEEDBACK_DICT = {
    1: "Eccomi! In che modalità vuoi andare?",
    2: "Non ho capito",
    3: "Non ho capito, prova a dire 'Wake up TGear'",
    
    100: "Orchestrator stopped",
    101: "Error. Orchestrator is set to combo but only one TSkin device is configured in hal.json",
    102: "Error. Orchestrator no device enabled in hal.json",
    103: "Waiting for TSkin(s) connection",
    104: "Waiting for IronBoy connection",
    105: "Waiting for Braccio connection",
    106: """
-------- Orchestrator application --------

Pronunciare "Wake up TGear" per attivare la routine di smistamento funzionalità:
    - pronunciare "I’m teaching you a lesson" per entrare in modalità Teacher
    - pronunciare "Please repeat what you learnt" per entrare in modalità Student
    - pronunciare "Please exit program" per terminare l'applicazione orchestratore

Modalità Teacher:

In questa modalità è possibile registrare una lezione attravero una combinazione di gesti e comandi vocali.
Una volta entrati nella modalità Teacher verra chiesto:
    - pronunciare la lezione che si desidera insegnare. Lezioni possibili:
        1) Say hello to our friends
        2) Please collect the ball
        3) Please move there
        4) Please drop it on the floow
    - inviare gesture attravero l'uso di uno o due TSkin (a seconda delle configurazioni).
        Se la gesture inviata richiede un parametro vocale è necessario pronunciarlo
    - quando si desidera salvare la lezione pronunciare "Please save program"
    - quando si desidera interrompere il comando in esecuzione pronunciare "Please stop command"

Modalità Student:

In questa modalità è possibile inviare a IronBoy dei comandi salvati in una lezione.
Una volta entrati nella modalità Student verrà chiesto:
    - pronunciare la lezione che si desidera eseguire. Lezioni possibili:
        1) Say hello to our friends
        2) Please collect the ball
        3) Please move there
        4) Please drop it on the floow

        Se viene indicata una lezione che non è stata registrata, appare un avviso a schermo
    - se si desidera interrompere in qualsiasi momento la modalità Student è possibile pronunciare "Please stop command"
        """,
    
    200: "Pronuncia la lezione desiderata:",
    201: "Ok! Ora puoi iniziare ad aggiungere comandi alla lezione, eseguendo gesture.",
    202: "Specificare comando vocale",
    203: "Il comando necessità di un ulteriore comando vocale che non è stato inviato. Rieseguire la gesture",
    204: "Ops! Il gesto che hai fatto non è presente tra le configurazioni...",
    205: "Error in ironboy command. Could not add command",
    206: "Error. Received wrong command from Ironboy [COMMAND MISMATCH]",
    207: "Sto salvando la macro, attendere...",
    208: "Macro salvata!",
    209: "Non è possibile salvare la macro mentre un comando è in esecuzione",
    210: "Interrompo il comando. Questo comando non verrà salvato nella macro.",
    211: "Non posso interrompere un comando perchè non c'è un comando in esecuzione",
    212: "Ops! Non è stato possibile completare il controllo del comando inviato. Per favore ripeti il comando inviato...",
    213: "Non è possibile identificare la lezione con i comandi inviati.",
    214: "Non è possibile inviare un nuovo comando. Aspettare il termine del comando corrente.",
    215: "Error in braccio command. Could not add command",
    216: "Error. Received wrong command from Braccio [COMMAND MISMATCH]",

    301: "Ops! Non è stato trovato il file della lezione, me la devi ancora insegnare!",
    302: "La lezione è stata eseguita correttamente!",
    303: "Error in ironboy command. Student stop",
    304: "Ops! Non è stato possibile completare il controllo del comando inviato. Non invio altri comandi.",
    305: "Ok! Eseguo la lezione che mi hai indicato",
    306: "Error in braccio command. Student stop",
    307: "Ops! Non è stato possibile completare il controllo del comando inviato. Non invio altri comandi.",

    400: "Iron boy BLE connected",
    401: "Iron boy BLE NOT detected",
    402: "BLE comunication corrupted. Restarting...",
    403: "Disconnecting IronBoy",
    404: "IronBoy disconnected",

    500: "Voice timeout - maybe you didn't say anything?",
    501: "Non ho trovato un comando valido",
    503: "Ascolto cercando un comando",
    504: "Smetto di ascoltare cercando un comando",
    505: "Ascoltando ho trovato un comando"
}

FEEDBACK_AUDIO = {
    1: "how_can_i_help_you.wav",
    2: "i_didnt_understand_the_command.wav",
    3: "i_didnt_understand_tgear.wav",
}


def millis():
    return time.time()*1000

class PipeFlusher(Process):

    RUNNING = 1
    STOPPED = 2

    def __init__(self, pipe: Connection):
        super(PipeFlusher, self).__init__(
            target=self._loop,
            args=(pipe,)
        )

        self.state = Value("b", self.RUNNING)

    @property
    def is_running(self):
        return self.state.value == self.RUNNING

    def _loop(self, pipe: Connection):
        while True:
            while self.state.value == self.RUNNING:
                if pipe != False and pipe.poll():
                    _ = pipe.recv()

    def stop(self):
        self.state.value = self.STOPPED

    def restart(self):
        self.state.value = self.RUNNING


def flush_pipe(pipe: Connection) -> None:
    """flush_pipe read the pipe until it's empty

    Args:
        pipe (Connection): The pipe to read
    """
    while pipe.poll():
        m = pipe.recv()
        del m
    return

# def command_in_trascript(trascripts, commands: Union[str, List[str]]) -> List[str]:
#     """command_in_trascript filters commands if are present in a trascript's candidate

#     Args:
#         trascripts (Transcripts_Message): transcript where to search
#         commands (Union[str, List[str]]): list of commands to be found

#     Returns:
#         List[str]: filtered list of command
#     """
#     if not type(commands) is list:
#         commands = [commands]

#     return [c for c in commands if c in trascripts]

def get_voice_phrase(pipe: Connection, timeout: int = 5) -> Union[None, any]:
    """get_voice_phrase gets phrase from speech pipe if found any within timeout

    Args:
        pipe (Connection): The pipe to get trancript from
        timeout (int, optional): execution timeout. Defaults to 5.

    Returns:
        Union[None, Phrase]: Transcript message if found, otherwise None
    """
    _t = 0

    while _t < timeout:
        if pipe.poll():
            return pipe.recv()
        else:
            time.sleep(0.1) 
            _t += 0.1
    
    raise TimeoutError

def phrases_routine(pipe: Connection, phrases: List[str]) -> Union[None, str]:
    """voice_routine Gets command from Speech pipe and check if those are valid

    Args:
        pipe (Connection): The speech pipe where transcripts are sent from
        phrases (List[Phrase]): List of phrases that can be found in the transcripts
        timeout (int, optional): Time (seconds) within which the recognition must be performed. Defaults to 5.

    Returns:
        Union[None, str]: Returns None if no commands are found, otherwise return the desired string.
    """

    def _internal(_pipe, _phrases, _timeout):
        _pipe.send(_phrases)

        try:
            phrase = get_voice_phrase(_pipe, _timeout)

        except TimeoutError as timeout_error:
            _pipe.send(timeout_error)
            pipe_msg = None
            if _pipe.poll(5):
                pipe_msg = _pipe.recv()
            else:
                user_feedback(FeedbackEnum.VOICE_TIMEOUT)

            if pipe_msg == TimeoutError:
                user_feedback(FeedbackEnum.VOICE_TIMEOUT)
                phrase = None
            else:
                phrase = pipe_msg

        if phrase != None:
            user_feedback(FeedbackEnum.VOICE_COMMAND_FOUND)
            return phrase

        user_feedback(FeedbackEnum.VOICE_DID_NOT_FOUND_ANYTHING)

        user_feedback(FeedbackEnum.VOICE_LISTENING_STOP)
        return None


    if not type(phrases) is list:
        phrases = [phrases]

    timeout_phrase = phrases[0].timeout

    flush_pipe(pipe)

    user_feedback(FeedbackEnum.VOICE_LISTENING_START)

    return _internal(pipe, phrases, timeout_phrase)

def user_feedback(_feedback: FeedbackEnum):
    
    print(FEEDBACK_DICT[_feedback.value])

# def user_feedback(_feedback: FeedbackEnum, _voice_process=None):

#     if _feedback.value not in FEEDBACK_AUDIO:
#         print(FEEDBACK_DICT[_feedback.value])
#         return

#     if _voice_process != None:
#         _voice_process.mute()

#     audio_file = path.join(AUDIO_FILE_DIR, FEEDBACK_AUDIO[_feedback.value])

#     wf = wave.open(audio_file, 'rb')
#     p = pyaudio.PyAudio()

#     stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
#                     channels=wf.getnchannels(),
#                     rate=wf.getframerate(),
#                     output=True)

#     data = wf.readframes(CHUNK)

#     while len(data):
#         stream.write(data)
#         data = wf.readframes(CHUNK)

#     stream.stop_stream()
#     stream.close()

#     p.terminate()

if __name__ == "__main__":
    user_feedback(FeedbackEnum.DIDNT_UNDERSTAND_TGEAR)