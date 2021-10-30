Things to do with a new Raspberry Pi to get this to work:
* Wire up the board and note the pins used for the switch and led
* Set the board up for headless
* Set up ssh keys
* Grab dropbox app key
* Run something like `sudo ln -s /home/pi/code/led.service /etc/systemd/system/led.service` to setup the led service
* `sudo systemctl daemon-reload` to pick this up
* `sudo journalctl -u led.service` to see the services logs
* Install requirements as root (TODO: set this up as an env)
* setup emails cred in the appropriate files (see led.py for file names)

Next things to do:
* More readable model output.  It's hard to interpret the bins.
* “Start” and end to indicate if a power outage occurred and how to deal with it.  It should be possible to detect if the log is corrupted and repair

Notes:
In retrospect, this might have all been silly.  The lamp gets turned on at pretty the same time every day so the predictive model isn't really useful
