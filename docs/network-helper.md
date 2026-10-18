# Optional in-app Wi-Fi setup

The app reads NetworkManager status without elevated privileges. Scanning and
connecting use `tools/network-helper.py`, a fixed JSON interface with connection
rollback. Install only on a machine where you want the radar account to manage
the `wlan0` Wi-Fi interface.

Install the helper as root-owned code, outside the writable checkout:

```sh
sudo install -d -o root -g root -m 755 /usr/local/lib/flight-radar
sudo install -o root -g root -m 644 tools/network-helper.py /usr/local/lib/flight-radar/network-helper.py
sudo visudo -f /etc/sudoers.d/flight-radar-network
```

Add this rule, replacing `RADAR_USER` with your actual local account name:

```sudoers
RADAR_USER ALL=(root) NOPASSWD: /usr/bin/python3 -I /usr/local/lib/flight-radar/network-helper.py
```

Then validate it:

```sh
sudo chmod 440 /etc/sudoers.d/flight-radar-network
sudo visudo -cf /etc/sudoers.d/flight-radar-network
```

The application sends credentials to the helper through standard input. Do not
grant passwordless execution of a helper inside a user-writable checkout.
Normal Raspberry Pi OS Wi-Fi configuration remains an alternative.
