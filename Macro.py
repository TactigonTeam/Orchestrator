import json
from os import path, listdir
from array import array
from enum import Enum

from IronBoy_Orchestrator import IronBoy_Msg_Command

class Command:

    ANGLE = 0
    GESTURE =  1

    def __init__(self, cmd_type: int, command: any, angles = None, iterations: int = 1):
        self.cmd_type = cmd_type
        self.command = command
        self.angles = angles
        self.iterations = iterations

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

    def add_command(self, command_msg: IronBoy_Msg_Command):
        new_cmd = Command(
            Command.GESTURE,
            command_msg.command,
            [],
            command_msg.iterations
        )
        self.commands.append(new_cmd)

    def save(self):
        obj = self.__dict__
        cmd_obj = [cmd.__dict__ for cmd in self.commands]

        obj["commands"] = cmd_obj

        file_path = path.join(path.dirname(__file__), "macro", self.filename)

        with open(file_path, "w") as macro_file:
            macro_file.write(json.dumps(obj, indent=2))
            macro_file.close()

    def load(self):
        file_path = path.join(path.dirname(__file__), "macro", self.filename)

        with open(file_path, "r") as macro_file:
            json_obj = json.load(macro_file)
            
        self.commands = [ Command(**cmd) for cmd in json_obj["commands"]]





if __name__ == "__main__":
    macro = Macro("test1")
    macro.add_command(IronBoy_Msg_Command(106, 1))
    macro.save()