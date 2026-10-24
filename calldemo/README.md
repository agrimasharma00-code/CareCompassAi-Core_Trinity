# Click-to-call demo

Run:

```powershell
python serve.py
```

Open the LAN URL printed by the server on a phone connected to the same Wi-Fi, then tap a button to open the dialer with the number prefilled. On desktop, `tel:` needs a handler, such as Phone Link on Windows or FaceTime on macOS. Browsers cannot place calls automatically; the dialer always asks for confirmation.

If a phone cannot connect, allow Python through the firewall.
