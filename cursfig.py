import yaml

def parse_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)
    return data

if __name__ == "__main__":
    yaml_file = "config.yaml"
    parsed_data = parse_yaml(yaml_file)
    print(parsed_data)
