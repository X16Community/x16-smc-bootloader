# Purpose

A custom bootloader for the Commander X16 ATtiny861 based System Management Controller (SMC).

The bootloader makes it possible to update the SMC firmware from the Commander X16 without an external programmer.


# How it works

## Firmware update process

A firmware update program runs on the X16 and sends the new SMC firmware to
the bootloader over I2C. 

The bootloader is responsible for checking the integrity of the transmitted data 
and for writing it to the flash memory of the SMC.

The transmission is divided into packets of nine bytes. A packets begins with
eight firmware bytes. The last byte is a checksum. The checksum is the 
2's complement of the sum of the previous eight bytes in the packet. I2C command 
offset 0x80 is used to transmit each byte of a packet.

A complete packet must committed using I2C command offset 0x81 before transmission
of the next packet is started.

The update process continues by transmitting and committing packets until the whole
firmware has been received by the bootloader.

The update program running on the X16 can optionally rewind the target address
to 0 using command 0x84 and use command 0x85 to read one byte at a time from
the SMC flash memory. The update program can use these functions to verify
the update.

Finally, the update program must use command 0x82 to reset the SMC. This will
write any buffered data to flash memory and then turn off the computer.

The SMC can only update the flash memory in whole pages of 64 bytes. The committed
bytes are buffered until there is a full page that can be written to flash memory.

On receiving the first full page (address 0x0000-0x003f), the bootloader takes
these special actions:

- Erasing the firmware area of the flash memory (address 0x0000-0x1dff)

- Moving the firmware's reset vector (address 0x0000) to EE_RDY (address 0x0012)

- Pointing the reset vector to the bootloader main vector (address 0x1e00)

The reason for this is explained in the SMC reset process below.


## SMC reset process

The SMC is reset when first connecting it to power or when 
reset pin #10 is grounded.  On reset, execution always starts at the reset vector (address 0x0000).

When the bootloader is installed, the reset vector always jumps to the bootloader main vector (address 0x1e00), 
as described above.

The bootloader main function checks if the Reset button is being pressed. 
If the button is pressed, the computer is powered on and the 
update process is started.

If the Reset button is not pressed, the bootloader jumps to
the EE_RDY vector (address 0x0012). The firmware's original
reset vector is moved here during the update process, as described above.


## Fail safe

The bootloader was designed to be as fail safe as possible:

- Firmware erase starts from the last page and ends with the
first page. If the update process is aborted during the erase
stage before the first page has been erased, the reset vector
is still unchanged. The recovery process update process can
be started by holding down the Reset button when connecting
power to the computer.

- If the update process fails after all pages have been
erased but before any new data has been written to flash memory,
execution will still end up at bootloader main vector, as 
erased firmware (value 0xff) is interpreted as NOPs.

- If the the update process fails after writing new data
to the first page, the reset vector will jump to the
bootloader main vector making it possible to do a
recovery update by holding down the Reset button.


## SMC memory map

| Byte address  | Size        | Description                |
|-------------- |-------------| ---------------------------|
| 0x0000-0x1DFF | 7,680 bytes | Firmware area              |
| 0x0000        | 2 bytes     | Reset vector               |
| 0x0012        | 2 bytes     | EE_RDY vector              |
| 0x1E00-0x1FFF | 512 bytes   | Bootloader area            |
| 0x1E00        | 2 bytes     | Bootloader main vector     |
| 0x1E02        | 2 bytes     | Start update vector        |
| 0x1FFE        | 2 bytes     | Bootloader version         |   


# Building the project

Type ```make``` to build the bootloader.

Build dependencies:

- make

- AVRA assembler https://github.com/Ro5bert/avra

- Python 3

- Python intelhex module, install with pip intelhex


# Fuse settings

The bootloader and the SMC firmware depend on several ATtiny fuse settings as set out below.

The recommended low fuse value is 0xF1. This will run the SMC at 16 MHz.

The recommended high fuse value is 0xD4. This enables Brown-out Detection at 4.3V, which is necessary to prevent flash memory corruption when self-programming is enabled. Serial Programming should be enabled (bit 5) and external reset disable should not be selected (bit 7). These settings are necessary for programming the SMC with an external programmer.

Finally, the extended fuse value must be 0xFE to enable self-programming of the flash memory. The bootloader cannot work without this setting.


# Initial programming of the SMC with avrdude

The initial programming of the SMC is done with an external programmer.

The command line utility avrdude is the recommended tool together
with a programmer that is compatible with avrdude.

Example 1. Set fuses
```
avrdude -cstk500v1 -Cavrdude.conf -pattiny861 -P<your port> -b19200 -Ulfuse:w:0xF1:m -Uhfuse:w:0xD4:m -Uefuse:w:0xFE:m
```

Example 2. Write to flash
```
avrdude -cstk500v1 -Cavrdude.conf -pattiny861 -P<your port> -b19200 -Uflash:w:build/firmware_with_bootloader.hex:i
```

The -c option selects programmer-id; stk500v1 is for using Arduino UNO as an In-System Programmer. If you have another ISP programmer, you may need to change this value accordingly.

The -p option selects the target device, always attiny861.

The -P option selects port name on the host computer.

The -b option sets transmission baudrate; 19200 is a good value.

The -U option performs a memory operation. "-U flash:w:filename:i" writes to flash memory. "-U lfuse:w:0xF1:m" writes the low fuse value.

Please note that some fuse settings may cause the ATtiny861 not to respond. Resetting might require equipment for high voltage programming. Be careful if you choose not to use the recommended values.

The Arduino IDE also uses avrdude in the background. If you have installed the IDE can use it to program the SMC, you may enable verbose output and see what parameters are used by the IDE when it starts avrdude.


# I2C API

## Command 0x80 = Transmit (master write)

The transmit command is used to send a data packet to the bootloader.

A packet consists of 8 bytes to be written to flash and 1 checksum byte.

The checksum is the two's complement of the least significant byte of the sum of the previous bytes in the packet. The least significant byte of the sum of all 9 bytes in a packet will consequently always be 0.

## Command 0x81 = Commit (master read)

After a data packet of 9 bytes has been transmitted it must be committed with this command. 

The first commit will target flash memory address 0x0000. The target address is moved forward 8 bytes on each successful commit.

The command returns 1 byte. The possible return values are:

Value | Description
------|-------------
1     | OK
2     | Error, packet size not 9
3     | Checksum error
4     | Reserved
5     | Error, overwriting bootloader section

The firmware flash memory are will be erased on the 8th successful commit, just before writing the first 64 bytes to flash memory.

## Command 0x82 = Reboot (master write)

The reboot command must always be called after the last packet
has been committed. If not, the SMC may be left in an inoperable
state.

The command first writes any buffered data to flash.

The bootloader then resets the SMC. The SMC reset shuts down the computer. It
can be restarted by pressing the power button. It is not necessary to power cycle the system
after an update.

## Command 0x83 = Get bootloader version (master read)

This command returns the bootloader version.

Available since bootloader v3.

## Command 0x84 = Rewind target address (master write)

Rewinds the target address to 0.

Available since bootloader v3.

## Command 0x85 = Read flash memory

Reads one byte of flash memory at the current target address.

The target address is post-incremented one byte.

This function is primarily intended to be used for verifying the
content of the flash memory after an update.

Available since bootloader v3.

