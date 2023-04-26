
import time
import asyncio
from enum import Enum
from bleak import BleakClient
from multiprocessing import Process, Pipe, Value
from multiprocessing.connection import Connection
from braccio.Solver import Solver

class Braccio_Command_Enum(Enum):
    HOME = 0
    COMMAND = 1
    TURN_ON = 2
    TURN_OFF = 3

class Wrist_Status_Enum(Enum):
    HORIZONTAL = 90
    VERTICAL = 0

class Gripper_Status_Enum(Enum):
    OPENED = 0
    CLOSED = 73

class Braccio_Msg_Command:

    def __init__(self, 
            x: int, 
            y: int, 
            z: int, 
            wrist: Wrist_Status_Enum = Wrist_Status_Enum.HORIZONTAL, 
            gripper: Gripper_Status_Enum = Gripper_Status_Enum.CLOSED, 
            command_type: Braccio_Command_Enum = Braccio_Command_Enum.COMMAND
        ):
        
        self.x = x
        self.y = y
        self.z = z

        if isinstance(wrist, Wrist_Status_Enum):
            self.wrist = wrist
        else:
            self.wrist = Wrist_Status_Enum(wrist)
        
        if isinstance(gripper, Gripper_Status_Enum):
            self.gripper = gripper
        else:
            self.gripper = Gripper_Status_Enum(gripper)

        if isinstance(command_type, Braccio_Command_Enum):
            self.command_type = command_type
        else:
            self.command_type = Braccio_Command_Enum(command_type)

        self._has_error = False
        self._is_completed = False
        self._is_timeout = False

    @classmethod
    def home(cls):
        return cls(0, 0, 0, command_type=Braccio_Command_Enum.HOME)

    @classmethod
    def on(cls):
        return cls(0, 0, 0, command_type=Braccio_Command_Enum.TURN_ON)

    @classmethod
    def off(cls):
        return cls(0, 0, 0, command_type=Braccio_Command_Enum.TURN_OFF)

    @property
    def is_completed(self):
        return self._is_completed

    @property
    def has_error(self):
        return self._has_error

    @property
    def timeout(self):
        return self._is_timeout

    async def wait_for_result(self, _timeout: int) -> bool:
        _t = 0
        while _t < _timeout * 10:
            if self._is_completed or self._has_error:
                return True
            
            _t += 1
            await asyncio.sleep(0.1)

        return False

    def set_complete(self):
        self._is_completed = True

    def set_error(self):
        self._has_error = True

    def set_timeout(self):
        self._is_timeout = True

    def __eq__(self, __o: object):
        if isinstance(__o, Braccio_Msg_Command):
            return self.x == __o.x and self.y == __o.y and self.z == __o.z and self.command_type == __o.command_type
        
        return False

    def __str__(self):
        return F"Braccio command. Type: {self.command_type}, coords: {self.x}, {self.y}, {self.z}, completed: {self._is_completed}, errors: {self._has_error}, timeout: {self._is_timeout}"

class Braccio_Msg_Command_List:
    def __init__(self, cmd_list: Braccio_Msg_Command):
        self.command_list = cmd_list

        self._has_error = False
        self._is_completed = False
        self._is_timeout = False

    @property
    def is_completed(self):
        return self._is_completed

    @property
    def has_error(self):
        return self._has_error

    @property
    def timeout(self):
        return self._is_timeout

    def set_complete(self):
        self._is_completed = True

    def set_error(self):
        self._has_error = True

    def set_timeout(self):
        self._is_timeout = True

    def __eq__(self, __o: object):
        if isinstance(__o, Braccio_Msg_Command_List):
            if len(self.command_list) != len(__o.command_list):
                return False
            
            for cmd1, cmd2 in zip(self.command_list, __o.command_list):
                if cmd1 != cmd2:
                    return False

            return True
        
        return False

    def __str__(self):
        return F"Braccio command list. {[c for c in self.command_list]}"

class Braccio(Process):

    RUNNING = 1
    STOPPING = 2
    STOPPED = 3

    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTING = 2
    DISCONNECTED = 3

    TIMEOUT = 20
    COMMAND_TIMEOUT_S = 10

    base =[0,0,180,0]  #default value for base, min value and max value, write location
    shoulder=[150,15,165,1]
    elbow=[0,0,180,2]
    wrist=[0,0,180,3]
    wristRot=[90,0,180,4]
    gripper=[73,73,0,5]

    def __init__(self, config, pipe: Connection):
        super(Braccio, self).__init__(
            target=self.setup,
            args=(config, pipe,)
        )
        self.state = Value("B", self.RUNNING)
        self._conn_state = Value("B", self.CONNECTING)

    @property
    def is_connected(self):
        return True if self._conn_state.value == self.CONNECTED else False

    def setup(self, config, pipe: Connection):
        self.ble_config = config["ble"]

        self.pipe = pipe
        self.solver = Solver()
        self.msg_command = None

        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.main())
        self.loop.run_forever()

    def serial_read(self, char, data: bytearray):
        recv = data.decode()
        
        if self.msg_command != None:
            if recv == "0":
                self.msg_command.set_complete()
            elif recv == "1":
                self.msg_command.set_error()
            elif recv == "2":
                self.msg_command.set_error()

    async def main(self):
        client = None

        while self.state.value == self.RUNNING:
            client = BleakClient(self.ble_config["address"])

            while self._conn_state.value == self.CONNECTING:
                self._conn_state.value = self.DISCONNECTED
                try:
                    await client.connect()
                    self._conn_state.value = self.CONNECTED
                    print("Braccio BLE connected")
                except:
                    print("Connecting Braccio BLE...")
                    self._conn_state.value = self.CONNECTING

                if client.is_connected:
                    try:
                        await client.start_notify(self.ble_config["status_characteristic"], self.serial_read)
                    except:
                        await client.disconnect()
                        self._conn_state.value = self.CONNECTING
                        

            while client.is_connected and self.state.value == self.RUNNING:
                if self.pipe.poll():
                    if self.msg_command == None:
                        msg_cmd_list: Braccio_Msg_Command_List = self.pipe.recv()
                        error = None

                        for msg_cmd in msg_cmd_list.command_list:

                            if error != None:
                                break

                            self.msg_command: Braccio_Msg_Command_List = msg_cmd

                            if self.msg_command.command_type == Braccio_Command_Enum.COMMAND:
                                angles = self.solver.move_to_position_cart(self.msg_command.x, self.msg_command.y, self.msg_command.z)

                                cmd = self.get_cmd(angles, self.msg_command.wrist, self.msg_command.gripper)
                            elif self.msg_command.command_type == Braccio_Command_Enum.HOME:
                                cmd = "H"
                            elif self.msg_command.command_type == Braccio_Command_Enum.TURN_ON:
                                cmd = "1"
                            else:
                                cmd = "0"
                        
                            try:
                                await client.write_gatt_char(self.ble_config["cmd_characteristic"], cmd.encode())
                            except Exception as e:
                                print(e)
                                print("Error in comunication, reconnect")
                                error = ConnectionRefusedError()

                            result = await self.msg_command.wait_for_result(self.COMMAND_TIMEOUT_S)
                            if not result:
                                error = TimeoutError

                        if isinstance(error, ConnectionRefusedError):
                            msg_cmd_list.set_error()
                            self.pipe.send(msg_cmd_list)
                            self.msg_command = None
                            break # Exit from the executing loop, we set conn as connecting after...
                        elif isinstance(error, TimeoutError):
                            msg_cmd_list.set_timeout()
                            self.pipe.send(msg_cmd_list)
                            self.msg_command = None
                        else:
                            msg_cmd_list.set_complete()
                            self.pipe.send(msg_cmd_list)
                            self.msg_command = None

                    else:
                        msg: Braccio_Msg_Command_List = self.pipe.recv()
                        msg.set_error()
                        self.pipe.send(msg)
                    
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.1)
            self._conn_state.value = self.CONNECTING

        if client != None :
            await client.disconnect()
            self._conn_state = self.DISCONNECTED

    def get_cmd(self, angles, wrist_angle: Wrist_Status_Enum = Wrist_Status_Enum.HORIZONTAL, gripper: Gripper_Status_Enum = Gripper_Status_Enum.CLOSED):
        # if gripper == Gripper_Status_Enum.CLOSED:
        #     theta_gripper=self.gripper[1]
        # else:
        #     theta_gripper=self.gripper[2]
        # angles[0]=180-angles[0]  #invert degrees for base
        # angles[3]=180-angles[3]  #invert degrees for base
        angle_string=','.join([str(elem) for elem in angles])  # join the list values togheter
        angle_string = F"P{angle_string},{wrist_angle.value},{gripper.value}|"
        return angle_string

    def stop(self):
        _t = 0

        print("Disconnecting Braccio BLE")
        self.state.value = self.STOPPING
        while self.is_connected and _t < self.TIMEOUT:
            time.sleep(1)
            _t += 1

        self.state.value = self.STOPPED
        print("Disconnected")
        return Process.terminate(self)


def cmd_routine(pipe, cmd):
    print(cmd)
    pipe.send(cmd)

    while not pipe.poll():
        time.sleep(0.1)

    ret = pipe.recv()
    if ret.is_completed:
        print("ok")
        return True
    
    print("error")
    return False


if __name__ == "__main__":
    import sys
    from os import path

    CLIENT_PY_PATH = path.join(path.dirname(__file__), "../../")
    sys.path.insert(0, path.join(CLIENT_PY_PATH, "utilities"))

    from Config_Manager import Config_Manager
    cfg = Config_Manager.from_file("apps/application_orchestrator_voice.json")
    braccio_config = cfg.get("braccio")

    p1, p2 = Pipe()

    braccio = Braccio(braccio_config, p1)
    braccio.start()

    print("connecting braccio")
    while not braccio.is_connected:
        time.sleep(1)

    print("braccio connected")

    # send stuff to pipe
    msg = Braccio_Msg_Command(100, 100, 100, Wrist_Status_Enum.HORIZONTAL)
    cmd_routine(p2, msg)

    msg = Braccio_Msg_Command(0, 0, 0, command_type=Braccio_Command_Enum.HOME)
    cmd_routine(p2, msg)

    msg = Braccio_Msg_Command(100, 0, 50)
    cmd_routine(p2, msg)

    msg = Braccio_Msg_Command(0, 0, 0, command_type=Braccio_Command_Enum.TURN_OFF)
    cmd_routine(p2, msg)

    msg = Braccio_Msg_Command(0, 0, 0, command_type=Braccio_Command_Enum.TURN_ON)
    cmd_routine(p2, msg)

    msg = Braccio_Msg_Command(100, 100, 100, Wrist_Status_Enum.HORIZONTAL)
    cmd_routine(p2, msg)

    msg = Braccio_Msg_Command(0, 0, 0, command_type=Braccio_Command_Enum.HOME)
    cmd_routine(p2, msg)

    msg = Braccio_Msg_Command(100, 100, 100, Wrist_Status_Enum.HORIZONTAL)
    cmd_routine(p2, msg)

    braccio.stop()



