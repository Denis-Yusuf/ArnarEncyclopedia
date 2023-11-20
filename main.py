from random import randint

def count_lines(file_path):
    with open(file_path, 'r') as file:
        line_count = sum(1 for line in file)
    return line_count


if __name__ == '__main__':
    path = "Arnar_Encyclopedia.txt"
    line_count = count_lines(path)
    f = open(path, "r")
    line = randint(0, line_count - 1)
    content = f.readlines()
    print(content[line])

