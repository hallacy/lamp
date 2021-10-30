# imports
import datetime
import random
import time

import dropbox
import fire
from dropbox.files import WriteMode

DEFAULT_SAVE_LOCATION = "/home/pi/code/state.txt"

DEFAULT_TOKEN_LOCATION = "/home/pi/.dropbox_token"

TOKEN = open(DEFAULT_TOKEN_LOCATION, "r").read().strip()


def save_to_backup(local_path, dropbox_path):
    with dropbox.Dropbox(TOKEN) as dbx:
        with open(local_path, "rb") as f:
            # We use WriteMode=overwrite to make sure that the settings in the file
            # are changed on upload
            print("Uploading " + local_path + " to Dropbox as " + dropbox_path + "...")
            dbx.files_upload(f.read(), dropbox_path, mode=WriteMode("overwrite"))


def load_from_backup():
    pass


def read_state_file_into_array(state_file):
    with open(state_file, "r") as f:
        lines = f.readlines()
    # Split each line on tab. The first field is a string, the second is an int
    return [[float(line.split("\t")[0]), int(line.split("\t")[1])] for line in lines]


class LampModel:
    def get_model_output(timestamp):
        raise NotImplementedError

    def train(data):
        raise NotImplementedError


class AverageOverLastXDays(LampModel):
    """Calculates the average value of the LED at a given timestamp
    over the past week and returns that value"""

    def __init__(self, days=7, interval_in_minutes=10, debug=False) -> None:
        self.model = None
        self.days = days
        self.interval_in_minutes = interval_in_minutes
        self.debug = debug

    def get_model_output(self, timestamp):
        timestamp = int(timestamp)
        if self.model is None:
            return 0
        else:
            return (
                self.model[
                    (timestamp // (self.interval_in_minutes * 60)) % len(self.model)
                ]
                * 100
            )

    def train(self, data):
        # Expecting input of [(timestamp, value), ...]
        # Filter for data in the last days days
        now_time = time.time()
        starting_time = time.time() - self.days * 24 * 60 * 60
        data = [x for x in data if x[0] > starting_time]

        # Create bins for each interval minutes of the day
        bins = []
        for i in range(24 * 60 // self.interval_in_minutes):
            bins.append([])

        cur_time = int(starting_time)
        # Walk through the data
        for i, d in enumerate(data):
            if i == len(data) - 1:
                next_d = None
                next_timestamp = None
            else:
                next_d = data[i + 1]
                next_timestamp = next_d[0]
            timestamp, value = d
            # Starting from the current time, walk through the bins.
            while (next_timestamp is None and cur_time < now_time) or (
                next_timestamp is not None
                and next_timestamp > cur_time + self.interval_in_minutes * 60
            ):
                bins[(cur_time // (self.interval_in_minutes * 60)) % len(bins)].append(
                    value
                )
                cur_time += self.interval_in_minutes * 60
            # TODO(hallacy): implement the case where the light turns on and off
            # multiple times in a single interval
            # For now, assume that a bin that changes always uses the last value

        # Calculate the average for each bin
        averages = []
        for bin in bins:
            if len(bin) == 0:
                averages.append(0)
            else:
                averages.append(sum(bin) / len(bin))
        if self.debug:
            print("Model Bins:", averages)

        self.model = averages


class SwitchStateTracker:
    def __init__(self, buf_length, threshold, debug, debug_printer):
        self.window = []
        self.buf_length = buf_length
        self.state = 0
        self.threshold = threshold
        self.debug = debug
        self.debug_counter = 0
        self.debug_printer = debug_printer

    # Feels like there's a race condition in here somewhere.  Probably should lock it
    def update(self, new_value):
        self.debug_counter += 1
        self.window.append(new_value)

        if len(self.window) > self.buf_length:
            self.window.pop(0)
            average = sum(self.window) / len(self.window)

            if self.debug and self.debug_counter % self.debug_printer == 0:
                self.debug_counter = 0
                print(f"WINDOW: {self.window}")
                print(f"AVERAGE: {average}")

            self.state = 1 if average >= self.threshold else 0

    def get_average(self):
        return sum(self.window) / len(self.window)

    def get_state(self):
        return self.state


class LED:
    def __init__(self, led_pin, led_freq, on_lamp, debug=False):
        self.cur_led_value = 0
        self.debug = debug

        if on_lamp:
            import RPi.GPIO as GPIO

            GPIO.setup(led_pin, GPIO.OUT)
            GPIO.output(led_pin, GPIO.LOW)

            self.p = GPIO.PWM(led_pin, led_freq)
            self.p.start(0)

    def update_led_state(self, new_value):

        if new_value != self.cur_led_value:
            if self.debug:
                print(f"LED: {new_value}")

            self.p.ChangeDutyCycle(new_value)
            self.cur_led_value = new_value

    def stop(self):
        self.p.stop()


def main(
    on_lamp=True,
    buf_length=100,
    debug_printer=100,
    counter=0,
    debug=False,
    loop_time=0.01,
    cur_state=False,
    threshold=0.75,
    test_mode=False,
    save_to_backup_every=1e6,
    state_file=DEFAULT_SAVE_LOCATION,
    load_from_backup=True,
    led_freq=100,
    test_threshold=0.6,
    train_every=100,
):

    # GPIO pins
    LED_PIN = 17
    SWITCH_PIN = 23

    # Set up the board
    if on_lamp:
        import RPi.GPIO as GPIO

        # setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(True)

        # setup
        GPIO.setup(SWITCH_PIN, GPIO.IN)
    led = LED(LED_PIN, led_freq, on_lamp, debug=debug)

    def get_switch_state():
        if on_lamp:
            return float(GPIO.input(SWITCH_PIN))
        else:
            return random.random()

    tracker = SwitchStateTracker(buf_length, threshold, debug, debug_printer)
    lamp_model = AverageOverLastXDays(days=7, interval_in_minutes=10, debug=debug)

    lamp_model.train(read_state_file_into_array(state_file))

    # Setup file that we're logging transitions to
    # Load from backup if it doesn't exist
    # if load_from_backup:
    #    load_from_backup()

    # I think we might want to do this by day instead of forever longer, but this will work for now
    with open(state_file, "a") as f:

        # main loop
        try:
            while True:
                start_time = time.time()
                counter += 1

                cur_val = get_switch_state()
                tracker.update(cur_val)

                if test_mode:
                    average = tracker.get_average()
                    debugged_cur_val = tracker.get_state()
                    # Normalize below X to be 0 and 1 to be 1
                    led_value = min(
                        max(
                            (average - test_threshold) * (1 / (1 - threshold)) * 100, 0
                        ),
                        100,
                    )
                    led.update_led_state(led_value)

                    if debugged_cur_val == 1 and cur_state is False:
                        print("SWITCH ON")
                        cur_state = True
                    elif debugged_cur_val == 0 and cur_state is True:
                        print("SWITCH OFF")
                        cur_state = False
                else:
                    debugged_cur_val = tracker.get_state()

                    # Update LED based on timestamp
                    led.update_led_state(lamp_model.get_model_output(time.time()))

                    if debugged_cur_val == 1 and cur_state is False:
                        print("SWITCH ON")
                        cur_state = True
                        # Use a lib
                        f.write(f"{start_time}\t{debugged_cur_val}")
                        f.write("\n")
                        f.flush()
                    elif debugged_cur_val == 0 and cur_state is True:
                        print("SWITCH OFF")
                        cur_state = False
                        # Use a lib
                        f.write(f"{start_time}\t{debugged_cur_val}")
                        f.write("\n")
                        f.flush()
                    if counter % train_every == 0:
                        print("Training")
                        lamp_model.train(read_state_file_into_array(state_file))
                    if counter % save_to_backup_every == 0:
                        save_to_backup(
                            state_file, f"/lamp_state_{int(time.time())}.txt"
                        )

                time_delta = time.time() - start_time
                if time_delta < loop_time:
                    time.sleep(loop_time - time_delta)
        except KeyboardInterrupt:
            print("Keyboard interrupt")
            save_to_backup(state_file, f"/lamp_state_{int(time.time())}.txt")
            led.stop()
            GPIO.cleanup()


if __name__ == "__main__":
    fire.Fire(main)
