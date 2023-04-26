import asyncio
import time
import orchestrator_lib as lib
from enum import Enum
from multiprocessing import Process, Value, Pipe
from multiprocessing.connection import Connection
from bleak import BleakClient

class IronBoy_Command_Enum(Enum):
    GESTURE = "G"
    ANGLE = "A"

class IronBoy_Msg_Command:

    NULL = 0
    COMMAND = 1
    ERROR = 2
    HALT = 3

    def __init__(self, command: any, iterations: int = 1, command_type: str = IronBoy_Command_Enum.GESTURE.value):
        self.command_type = command_type
        self.command = command
        self.iterations = iterations
        self.executed_iterations = 0
        self.state = IronBoy_Msg_Command.COMMAND

    @classmethod
    def from_macro_command(cls, command):
        return cls(command.command, command.iterations)

    @classmethod
    def null_command(cls):
        _c = cls("", 0)
        _c.state = IronBoy_Msg_Command.NULL
        return _c

    @classmethod
    def halt_command(cls):
        _c = cls(Ironboy_Feedback_Enum.STOP.value, 1)
        _c.state = IronBoy_Msg_Command.HALT
        return _c

    @property
    def is_null(self) -> bool:
        return self.state == IronBoy_Msg_Command.NULL

    @property
    def is_running(self) -> bool:
        return self.state == IronBoy_Msg_Command.COMMAND and self.executed_iterations < self.iterations

    @property
    def is_completed(self) -> bool:
        return self.state == IronBoy_Msg_Command.COMMAND and self.iterations == self.executed_iterations

    @property
    def has_error(self) -> bool:
        return self.state == IronBoy_Msg_Command.ERROR

    @property
    def is_halt(self) -> bool:
        return self.state == IronBoy_Msg_Command.HALT

    def force_halt(self) -> None:
        self.state = IronBoy_Msg_Command.HALT

    def force_error(self) -> None:
        self.state = IronBoy_Msg_Command.ERROR

    def done_one(self):
        self.executed_iterations += 1

    async def wait_for_done_one(self, _timeout: int) -> bool:
        _old_executed_iterations = self.executed_iterations

        _t = 0
        while _old_executed_iterations == self.executed_iterations:
            await asyncio.sleep(0.1)
            _t += 1

            if _t == _timeout*10:
                return False

        return True

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, IronBoy_Msg_Command):
            return self.command == __o.command and self.iterations == __o.iterations

        return False

    def __str__(self):
        state_def = ("NULL", "COMMAND", "ERROR", "HALT")
        return F"IronBoy_Msg_Command: {self.command_type} {self.command} ({self.iterations} iteration). Current state {state_def[self.state]} ({self.state})"

class IronBoy(Process):

    RUNNING = 1
    STOPPING = 2
    STOPPED = 3

    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTING = 2
    DISCONNECTED = 3

    ACK_OK = 255
    TIMEOUT_S = 20

    # COMMAND_DIC = {
    #     "STAND": 106,
    #     "SIT_DOWN": 107,

    #     "WALK_FWD": 2,
    #     "TURN_L": 3,
    #     "TURN_R": 4,
    #     "WALK_BACK": 5,
    #     "TIPTOE_FWD": 8,
    #     "TIPTOE_L": 9,
    #     "TIPTOE_R": 10,
    #     "TIPTOE_BACK": 11,

    #     "VICTORY" : 6,
    #     "WAVE": 50,
    #     "DANCE": 51,
    #     "NO_COMMAND": 255,

    #     # "WALK_FWD": 100,
    #     # "TURN_L": 101,
    #     # "TURN_R": 102,
    #     # "WALK_BACK": 103,
    #     # "SIDE_STEP_L": 104,
    #     # "SIDE_STEP_R": 105,
    #     # "STAND": 106, 
    #     # "SIT_DOWN": 107,
    #     # "GET_UP_FWD": 108,
    #     # "GET_UP_BACK": 109,
    #     # "BODY_SIDE_TILT": 110,
    #     # "PROVOKE": 111,
    #     # "PUSHUP": 112,
    #     # "SIDE_KICK_L": 113,
    #     # "SIDE_KICK_R": 114,
    # }

    def __init__(self, config, pipe: Connection) -> None:
        """__init__ is an interface to send and receive commands to IronBoy robot using BLE moduloe BlueFruit (UART mode)

        Args:
            config: An object containing:
                {
                    "ble": {
                        "address": (str) MAC address,
                        "status_characteristic": (str) GATT address to read status from,
                        "cmd_characteristic": (str) GATT address to send command to
                    }
                }
            pipe (Connection): Connection to Orchestrator. Command will be sent here.
        """
        super(IronBoy, self).__init__(
            target=self._loop,
            args=(config, pipe,),
        )

        self.state = Value("B", IronBoy.RUNNING)
        self._is_connected = Value("B", IronBoy.DISCONNECTED)

    @property
    def is_connected(self) -> bool:
        return True if self._is_connected.value == IronBoy.CONNECTED else False

    def _loop(self, config, pipe):
        # member init
        self.ble_config = config["ble"]
        self.commands = config["commands"]

        self.pipe = pipe
        self.ack = self.ACK_OK
        self.msg_command = IronBoy_Msg_Command.null_command()

        loop = asyncio.get_event_loop()
        loop.create_task(self._run())
        loop.run_forever()

    async def _run(self):
        conn_state = self.CONNECTING
        client = None

        while self.state.value == self.RUNNING:
            client = BleakClient(self.ble_config["address"])
            
            while conn_state == self.CONNECTING:
                self._is_connected.value = self.DISCONNECTED
                try:
                    await client.connect()
                    # print("Iron boy BLE", client.address, "connected")
                    lib.user_feedback(lib.FeedbackEnum.IRONBOY_CONNECTED)
                except:
                    # print("Iron boy BLE", client.address, "not detected")
                    lib.user_feedback(lib.FeedbackEnum.IRONBOY_NOT_CONNECTED)

                if client.is_connected:
                    conn_state = self.CONNECTED
                    self._is_connected.value = self.CONNECTED
                    lib.flush_pipe(self.pipe)
                    try:
                        await client.start_notify(self.ble_config["status_characteristic"], self._get_ack)
                    except:
                        # print("BLE comunication corrupted. Restarting...")
                        lib.user_feedback(lib.FeedbackEnum.IRONBOY_CONNECTION_ERROR)
                        await client.disconnect()
                        self.msg_command.force_error()
                        self.pipe.send(self.msg_command)
                        self.msg_command = IronBoy_Msg_Command.null_command()
                        conn_state = self.CONNECTING

            while conn_state == self.CONNECTED:
                if not client.is_connected:
                    conn_state = self.CONNECTING

                if self.pipe.poll():
                    new_msg_command = self.pipe.recv()
                    if new_msg_command.state == IronBoy_Msg_Command.COMMAND:
                        if self.msg_command.is_null or self.msg_command.is_halt:
                            self.msg_command = new_msg_command

                    elif new_msg_command.state == IronBoy_Msg_Command.HALT:
                        self.msg_command = new_msg_command

                if self.msg_command.is_running or self.msg_command.is_halt:
                    # command = self.msg_command.command
                    # command_number = IronBoy.COMMAND_DIC[command]
                    command_type = self.msg_command.command_type
                    if command_type == IronBoy_Command_Enum.GESTURE.value:
                        command = self.commands[self.msg_command.command]
                    else:
                        command = self.msg_command.command
                    
                    byte_command = bytearray(F"{command_type}{command}|", "UTF-8")
                    
                    try:
                        await client.write_gatt_char(self.ble_config["cmd_characteristic"], byte_command)
                    except:
                        lib.user_feedback(lib.FeedbackEnum.IRONBOY_CONNECTION_ERROR)
                        conn_state = self.CONNECTING
                        break

                    if self.msg_command.command_type == IronBoy_Command_Enum.GESTURE.value:
                        result = await self.msg_command.wait_for_done_one(self.TIMEOUT_S)
                    else:
                        self.msg_command.executed_iterations = 1
                        result = True

                    if not result:
                        self.msg_command.force_error()
                    
                    self.pipe.send(self.msg_command)

                if self.msg_command.is_completed or self.msg_command.is_halt:
                    self.msg_command = IronBoy_Msg_Command.null_command()

                await asyncio.sleep(0.1)

        if client != None :
            await client.disconnect()
            conn_state = self.DISCONNECTED

    def _get_ack(self, char, data: bytearray):
        new_command_number = int.from_bytes(data, 'little')

        if self.msg_command.is_running or self.msg_command.is_halt:
            if self.ack != new_command_number and new_command_number == IronBoy.ACK_OK:
                # Done executing one command, send message to keepalive
                self.msg_command.done_one()

        self.ack = new_command_number


    def stop(self) -> None:
        self.state.value = IronBoy.STOPPING
        # print("Disconnecting IronBoy")
        lib.user_feedback(lib.FeedbackEnum.IRONBOY_DISCONNECTING)

        timeout = 0
        while self.state.value != IronBoy.STOPPED and timeout < IronBoy.TIMEOUT_S:
            timeout = timeout + 1
            time.sleep(0.1)
        # print("Disconnection time: {:.1f} sec".format(timeout * 0.1))
        lib.user_feedback(lib.FeedbackEnum.IRONBOY_DISCONNECTED)

        return Process.terminate(self)

class Ironboy_Feedback_Enum(Enum):
    GESTURE_NOT_FOUND = "GESTURE_NOT_FOUND"
    VOICE_NOT_FOUND = "VOICE_NOT_FOUND"
    EXPECT_VOICE_COMMAND = "VOICE_COMMAND"
    STUDENT_END = "STUDENT_END"
    STOP = "NOK_MSG"

def ironboy_feedback(_pipe: Connection, _feedback: Ironboy_Feedback_Enum, ball_lesson=False):
    cmd = _feedback.value
    if ball_lesson:
        cmd = cmd + "_BALL"
    _pipe.send(IronBoy_Msg_Command(cmd, 1))
    if _pipe.poll(5):
        _pipe.recv()

# if __name__ == "__main__":
#     import sys
#     from os import path

#     CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
#     sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))

#     from Config_Manager import Config_Manager

#     pipe1, pipe2 = Pipe()

#     cfg = Config_Manager.from_file("apps/application_orchestrator_voice.json")
#     ib_cfg = cfg.get("ironboy")
#     ib = IronBoy(ib_cfg, pipe1)

#     ib.start()

#     while not ib.is_connected:
#         print("connecting")
#         time.sleep(1)

#     cmd1 = IronBoy_Msg_Command("WALK_FWD", 10)
#     # cmd2 = IronBoy_Msg_Command("pull", 1)

#     pipe2.send(cmd1)
#     print("Sending command")
#     # pipe2.send(cmd2)
#     cmd_r = None

#     _t = 0

#     while cmd1.is_running:
#         print("wait")
#         time.sleep(0.1)

#         _t += 0.1

#         if pipe2.poll():
#             cmd1 = pipe2.recv()

#         if cmd1.is_completed:
#             print("ok")
#             break

#     print("Command executed")
#     ib.stop()