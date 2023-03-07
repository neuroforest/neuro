from neuro.tools.api import tw_actions


def is_text_ok(text):
    if any([x for x in text if x in "[{|}]"]):
        return False
    else:
        return True


def replace_text(old_text, new_text, tw_filter):
    """
    Replace text in all fields, special characters [ { | } ] are not allowed.
    :param old_text:
    :param new_text:
    :param tw_filter:
    :return:
    """
    if is_text_ok(old_text) and is_text_ok(new_text):
        tw_actions.replace_text(old_text, new_text, tw_filter=tw_filter)
        return True
    else:
        print("Error: Forbidden characters found: [ { | } ]")
        return False
