from PIL import Image

# Open your logo image (make sure file name is exact)
img = Image.open("static/images/tech computer logo.jpeg")

# Resize the image to 32x32 pixels
img = img.resize((32, 32))

# Save as favicon.ico inside static directory
img.save("static/favicon.ico", format="ICO")

print("Favicon created successfully as static/favicon.ico")
