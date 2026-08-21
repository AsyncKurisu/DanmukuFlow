import math


def format_ass_time(value):
    secs = int(math.floor(value))
    hour = secs // 3600
    minutes = (secs % 3600) // 60
    left = value - float(hour * 3600) - float(minutes * 60)
    return "{}:{:02}:{:05.2f}".format(hour, minutes, left)
