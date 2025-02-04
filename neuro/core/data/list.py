class ListUtils:
    @staticmethod
    def represent(li, level=0, display=True):
        representation_string = str()
        for i in li:
            representation_string += f"{(level + 1) * '    '}{i}\n"
        representation_string += f"{level * '    '}]\n"

        if display:
            print(representation_string)
        else:
            return representation_string
