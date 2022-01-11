def is_float(s):
    result = False

    try:
        float(s)
        result = True
    except ValueError:
        pass

    return result
