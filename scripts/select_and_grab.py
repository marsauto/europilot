from PIL import Image

from europilot.screen import ScreenUtils, LocalScreenGrab

# Select game screen
box = ScreenUtils.select_screen_area()

# Grab selected area
local_grab = LocalScreenGrab(box)
arr = local_grab.grab()
arr = arr.reshape(box.numpy_shape)

# Show image
image = Image.fromarray(arr, 'RGB')
image.show()
