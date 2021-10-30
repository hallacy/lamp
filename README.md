Things to do with a new Raspberry Pi to get this to work:
* Wire up the board and note the pins used for the switch and led
* Set the board up for headless
* Set up ssh keys
* Grab dropbox app key
* Run something like `sudo ln -s /home/pi/code/led.service /etc/systemd/system/led.service` to setup the led service
* `sudo systemctl daemon-reload` to pick this up
* `sudo journalctl -u led.service` to see the services logs
* Install requirements as root (TODO: set this up as an env)
