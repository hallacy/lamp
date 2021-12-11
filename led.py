# imports
import datetime
import random
import smtplib
import time
import traceback

import dropbox
import fire
import RPi.GPIO as GPIO
from dropbox.files import WriteMode

DEFAULT_SAVE_LOCATION = "/home/pi/code/state.txt"


# DROPBOX
DEFAULT_TOKEN_LOCATION = "/home/pi/.dropbox_token"
TOKEN = open(DEFAULT_TOKEN_LOCATION, "r").read().strip()

# Email Variables
SMTP_SERVER = "smtp.gmail.com"  # Email Server (don't change!)
SMTP_PORT = 587  # Server Port (don't change!)
GMAIL_USERNAME = open("/home/pi/.gmail_username", "r").read().strip()
GMAIL_PASSWORD = open("/home/pi/.gmail_password", "r").read().strip()
RECEIVER_EMAIL = open("/home/pi/.reciever_email", "r").read().strip()


def save_to_backup(local_path, dropbox_path):
    with dropbox.Dropbox(TOKEN) as dbx:
        with open(local_path, "rb") as f:
            # We use WriteMode=overwrite to make sure that the settings in the file
            # are changed on upload
            print("Uploading " + local_path + " to Dropbox as " + dropbox_path + "...")
            dbx.files_upload(f.read(), dropbox_path, mode=WriteMode("overwrite"))


def read_state_file_into_array(state_file):
    with open(state_file, "r") as f:
        lines = f.readlines()
    # Split each line on tab. The first field is a float, the second is an int
    return [
        [float(line.split("\t")[0]), float(line.split("\t")[1]), line.split("\t")[2]]
        for line in lines
    ]


class Emailer:
    def sendmail(self, recipient, subject, content):

        # Create Headers
        headers = [
            "From: " + GMAIL_USERNAME,
            "Subject: " + subject,
            "To: " + recipient,
            "MIME-Version: 1.0",
            "Content-Type: text/html",
        ]
        headers = "\r\n".join(headers)

        # Connect to Gmail Server
        session = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        session.ehlo()
        session.starttls()
        session.ehlo()

        # Login to Gmail
        session.login(GMAIL_USERNAME, GMAIL_PASSWORD)

        # Send Email & Exit
        session.sendmail(GMAIL_USERNAME, recipient, headers + "\r\n\r\n" + content)
        session.quit


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
        cur_value = 0
        # Walk through the data, assume sorted
        for i, d in enumerate(data):
            timestamp, next_value, additional_data = d
            additional_data = additional_data.strip()

            # Starting from the current time, walk through the bins.
            while timestamp > cur_time:
                # if self.debug:
                #     print(
                #         f"Cur time is: {time_to_human(cur_time)}.  Iterating to {additional_data}. Setting to {cur_value}"
                #     )
                #     time.sleep(0.1)

                bins[(cur_time // (self.interval_in_minutes * 60)) % len(bins)].append(
                    cur_value
                )
                cur_time += self.interval_in_minutes * 60
            cur_value = next_value
            # TODO(hallacy): implement the case where the light turns on and off
            # multiple times in a single interval
            # For now, assume that a bin that changes always uses the last value

        # If we've iterated through the data and there's still time before the present:
        while cur_time < now_time:
            # if self.debug:
            #     print(
            #         f"Cur time is: {time_to_human(cur_time)}.  Iterating to {time_to_human(now_time)}. Setting to {cur_value}"
            #     )
            #     time.sleep(0.1)

            bins[(cur_time // (self.interval_in_minutes * 60)) % len(bins)].append(
                cur_value
            )
            cur_time += self.interval_in_minutes * 60

        # Calculate the average for each bin
        if self.debug:
            print("Model Bins:", bins)
        averages = []
        for bin in bins:
            if len(bin) == 0:
                averages.append(0)
            else:
                averages.append(sum(bin) / len(bin))
        if self.debug:
            print("Model Averages:", averages)

        self.model = averages


class LED:
    def __init__(self, led_pin, led_freq, on_lamp, debug=False):
        self.cur_led_value = 0
        self.debug = debug

        if on_lamp:
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


def time_to_human(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%A, %d. %B %Y %I:%M%p")


def write_to_log(f, timestamp, value):
    # All times are pacific
    dateinfo = time_to_human(timestamp)
    print(f"Light Changed: {timestamp}\t{value}\t{dateinfo}")
    f.write(f"{timestamp}\t{value}\t{dateinfo}")
    f.write("\n")
    f.flush()


def sos_mode(exception, led):
    try:
        # Send an email to me
        print("Sending email")
        sender = Emailer()

        sendTo = RECEIVER_EMAIL
        emailSubject = f"SOS Mode on Lamp at {datetime.datetime.isoformat(datetime.datetime.now())} EOM"
        emailContent = traceback.format_exc()

        sender.sendmail(sendTo, emailSubject, emailContent)
    except Exception as e:
        print(e)

    # Repeat SOS led pattern
    print("SOS led pattern active")
    try:
        while True:
            led.update_led_state(100)
            time.sleep(0.5)
            led.update_led_state(0)
            time.sleep(0.5)
    except KeyboardInterrupt:
        led.stop()
        GPIO.cleanup()


def main(
    on_lamp=True,
    buf_length=100,
    debug_printer=100,
    counter=0,
    debug=False,
    loop_time=0.01,
    cur_state=None,
    threshold=0.75,
    test_mode=False,
    save_to_backup_every=1e7,
    state_file=DEFAULT_SAVE_LOCATION,
    load_from_backup=True,
    led_freq=100,
    test_threshold=0.6,
    train_every=1e6,
):

    # GPIO pins
    LED_PIN = 17
    SWITCH_PIN = 23

    # Set up the board
    if on_lamp:

        # setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(True)

        # setup
        GPIO.setup(SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    led = LED(LED_PIN, led_freq, on_lamp, debug=debug)

    def get_switch_state():
        if on_lamp:
            return float(GPIO.input(SWITCH_PIN))
        else:
            return random.random()

    lamp_model = AverageOverLastXDays(days=7, interval_in_minutes=10, debug=debug)

    lamp_model.train(read_state_file_into_array(state_file))

    try:
        with open(state_file, "a") as f:
            # main loop
            try:
                while True:
                    start_time = time.time()
                    counter += 1

                    cur_val = get_switch_state()

                    if test_mode:
                        led.update_led_state(cur_val * 100)

                        if cur_val > 0.5 and cur_state == 0:
                            print("SWITCH ON")
                            cur_state = cur_val
                        elif cur_val < 0.5 and cur_state == 1:
                            print("SWITCH OFF")
                            cur_state = cur_val
                    else:

                        # Update LED based on timestamp
                        led.update_led_state(lamp_model.get_model_output(time.time()))

                        if cur_val == 1 and cur_state == 0:
                            print("SWITCH ON")
                            cur_state = cur_val
                            write_to_log(f, start_time, cur_val)
                        elif cur_val == 0 and cur_state == 1:
                            print("SWITCH OFF")
                            cur_state = cur_val
                            write_to_log(f, start_time, cur_val)
                        elif cur_state is None:
                            cur_state = cur_val
                            write_to_log(f, start_time, cur_val)

                        # Training
                        if counter % train_every == 0:
                            print("Training")
                            lamp_model.train(read_state_file_into_array(state_file))

                        # Backup
                        if counter % save_to_backup_every == 0:
                            # Drop box notes that long lasting tokens might get deprecated in the future
                            save_to_backup(
                                state_file, f"/lamp_state_{int(time.time())}.txt"
                            )

                    time_delta = time.time() - start_time
                    if time_delta < loop_time:
                        time.sleep(loop_time - time_delta)
            except KeyboardInterrupt:
                print("Keyboard interrupt")
    except Exception as e:
        sos_mode(e, led)
    finally:
        print("Cleaning up")
        save_to_backup(state_file, f"/lamp_state_{int(time.time())}.txt")
        led.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    fire.Fire(main)
