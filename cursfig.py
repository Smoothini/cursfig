import yaml, pprint, os, filecmp

class PConfig:
    def __init__(self, name, files, folders):
        self.name = name
        self.files = files
        self.folders = folders

def parse_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)
    return data

def is_newer(path1, path2):
    mod_time1 = os.path.getmtime(path1)
    mod_time2 = os.path.getmtime(path2)

    if mod_time1 > mod_time2:
        print(f"{path1} is newer")
    elif mod_time1 < mod_time2:
        print(f"{path2} is newer")
    else:
        print("Files have the same modification time")

def is_same(path1, path2):
    if filecmp.cmp(path1, path2, shallow=False):  # shallow=False forces full comparison
        print("Files are identical")
    else:
        print("Files are different")


if __name__ == "__main__":
    yaml_file = "configs/default/cursfig.yaml"
    parsed_data = parse_yaml(yaml_file)
    pprint.pp(parsed_data)
