from intelhex import IntelHex

# Load HEX file
bootloader = IntelHex()
bootloader.fromfile("build/bootloader.hex", format="hex")

# Validate start of bootloader != 0x8a
#   Before bootloader v3, 0x1e00 was set to the magic value 0x8a to indicate that
#   a bootloader was present. From bootloader v3 the magic value and version
#   number has been moved to the end of flash memory (0x1ffe-0x1fff).
#   The start of the bootloader is expected to be a table of rjmp instructions.
#   There is one rjmp instruction with a target address within the bootloader area
#   where the low byte is 0x8a. This rjmp instruction should consequently be avoided.
#   This script exits with an error code to remind us about the above.
if bootloader[0] == 0x8a:
    print("ERROR: The bootloader may not start with byte value 0x8a.")
    exit(1)

# Create bin file
bootloader.tofile("build/bootloader.bin", format="bin")
