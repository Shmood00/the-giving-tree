import uasyncio
from led_touch import listen

print("TEST")
uasyncio.run(listen())
