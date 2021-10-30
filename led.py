# imports
import random
import time

import fire

DEFAULT_SAVE_LOCATION = "/Users/hallacy/lamp_state.txt"


def save_to_backup():
    pass


def load_from_backup():
    pass


class LampModel:
    def get_model_output(timestamp):
        raise NotImplementedError

    def train(data):
        raise NotImplementedError


class AverageOverLastWeek(LampModel):
    """Calculates the average value of the LED at a given timestamp
    over the past week and returns that value"""

    def get_model_output(timestamp):
        raise NotImplementedError

    def train(data):
        raise NotImplementedError


class SwitchStateTracker:
    def __init__(self, buf_length, threshold, allow_debug, debug_printer):
        self.window = []
        self.buf_length = buf_length
        self.state = 0
        self.threshold = threshold
        self.allow_debug = allow_debug
        self.debug_counter = 0
        self.debug_printer = debug_printer

    # Feels like there's a race condition in here somewhere.  Probably should lock it
    def update(self, new_value):
        self.debug_counter += 1
        self.window.append(new_value)

        if len(self.window) > self.buf_length:
            self.window.pop(0)
            average = sum(self.window) / len(self.window)

            if self.allow_debug and self.debug_counter % self.debug_printer == 0:
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

            self.p = GPIO.PWM(led_pin, led_freq)
            self.p.start(0)

    def update_led_state(self, new_value):

        if new_value != self.cur_led_value:
            if self.debug:
                print(f"LED: {new_value}")

            self.p.ChangeDutyCycle(new_value)
            self.cur_led_value = new_value


def main(
    on_lamp=True,
    buf_length=100,
    debug_printer=100,
    counter=0,
    allow_debug=False,
    loop_time=0.01,
    cur_state=False,
    threshold=0.75,
    test_mode=False,
    save_to_backup_every=1e6,
    state_file=DEFAULT_SAVE_LOCATION,
    load_from_backup=True,
    led_freq=100,
    test_threshold=0.6,
):

    # GPIO pins
    LED_PIN = 18
    SWITCH_PIN = 25

    # Set up the board
    if on_lamp:
        import RPi.GPIO as GPIO

        # setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # setup
        GPIO.setup(SWITCH_PIN, GPIO.IN)
    led = LED(LED_PIN, led_freq, on_lamp, debug=allow_debug)

    def get_switch_state():
        if on_lamp:
            return float(GPIO.input(SWITCH_PIN))
        else:
            return random.random()

    tracker = SwitchStateTracker(buf_length, threshold, allow_debug, debug_printer)

    # Setup file that we're logging transitions to
    # Load from backup if it doesn't exist
    # if load_from_backup:
    #    load_from_backup()

    # I think we might want to do this by day instead of forever longer, but this will work for now
    with open(state_file, "a") as f:

        # main loop
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
                    max((average - test_threshold) * (1 / (1 - threshold)) * 100, 0),
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
            if counter % save_to_backup_every == 0:
                save_to_backup()

            time_delta = time.time() - start_time
            if time_delta < loop_time:
                time.sleep(loop_time - time_delta)


if __name__ == "__main__":
    fire.Fire(main)
