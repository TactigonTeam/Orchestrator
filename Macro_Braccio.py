import json
from os import path

from Braccio_Orchestrator import Braccio_Msg_Command, Wrist_Status_Enum, Gripper_Status_Enum, Braccio_Command_Enum

class Command:
    def __init__(self, x: int, y: int, z: int, wrist: Wrist_Status_Enum, gripper: Gripper_Status_Enum, command_type: Braccio_Command_Enum):
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

    @property
    def __dict__(self):
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "wrist": self.wrist.value,
            "gripper": self.gripper.value,
            "command_type": self.command_type.value,
        }

class Macro:  
    def __init__(self, name: str, filename: str = ""):
        """The Macro class interfaces the Teacher and Student class.
        It is a container of commands that can be read and written to a JSON file

        Args:
            name (str): Macro name
            filename (str, optional): Macro filename. If not empty the macro will be automatically loaded from said file. Defaults to "".
        """
        self.name = name
        self.filename = filename
        self.commands = []

        if filename:
            self.load()
        else:
            self.filename = name + ".json"

    def add_command(self, command_msg: Braccio_Msg_Command):
        new_cmd = Command(
            command_msg.x,
            command_msg.y,
            command_msg.z,
            command_msg.wrist,
            command_msg.gripper,
            command_msg.command_type            
        )
        self.commands.append(new_cmd)

    def save(self):
        obj = self.__dict__
        cmd_obj = [cmd.__dict__ for cmd in self.commands]

        obj["commands"] = cmd_obj

        file_path = path.join(path.dirname(__file__), "macro_braccio", self.filename)

        with open(file_path, "w") as macro_file:
            macro_file.write(json.dumps(obj, indent=2))
            macro_file.close()

    def load(self):
        file_path = path.join(path.dirname(__file__), "macro_braccio", self.filename)

        with open(file_path, "r") as macro_file:
            json_obj = json.load(macro_file)
            
        self.commands = [ Command(**cmd) for cmd in json_obj["commands"]]





if __name__ == "__main__":
    macro = Macro("test1")
    macro.add_command(Braccio_Msg_Command(100, 100, 100, Wrist_Status_Enum.VERTICAL, Gripper_Status_Enum.CLOSED))
    macro.add_command(Braccio_Msg_Command(0, 0, 0, Wrist_Status_Enum.VERTICAL, Gripper_Status_Enum.CLOSED, Braccio_Command_Enum.HOME))
    macro.save()