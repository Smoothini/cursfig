class ProgramConfig:
    def __init__(self, name, files, folders):
        self.name = name
        self.files = files
        self.folders = folders

    def pprint(self):
        print("--------------")
        print(f"Program: {self.name}")
        print("Files: ")
        if len(self.files) > 0:
            for file in self.files:
                fileprint = "  - "
                pathprint = f"    found at {file["path_win"]}"
                for f in file["files"]:
                    fileprint += f"{f}, "
                print(fileprint)
                print(pathprint)
        else:
            print("no files!")

        
        print("Folders: ")
        if len(self.folders) > 0:
            for folder in self.folders:
                folderprint = "  - "
                pathprint = f"    found at {folder["path_win"]}"
                for f in folder["folders"]:
                    folderprint += f"{f}, "
                print(folderprint)
                print(pathprint)
        else:
            print("no folders!")



class CursedConfig:
    def __init__(self, programs: list[ProgramConfig]):
        self.programs = programs