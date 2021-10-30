import datetime
import time
from time import localtime, strftime

file = "/Users/hallacy/Downloads/lamp_state_1635609191.txt"

with open(file, "r") as f:
    for line in f:
        line = line.strip()
        pieces = line.split("\t")
        timestamp, state = pieces[0], pieces[1]
        timestamp = float(timestamp)

        #'Saturday, 30. October 2021 09:06AM'
        dateinfo = datetime.datetime.fromtimestamp(timestamp).strftime(
            "%A, %d. %B %Y %I:%M%p"
        )

        print(f"{timestamp}\t{state}\t{dateinfo}")
